#!/usr/bin/env bash
# is_archive_ok.sh -- Validates a student ZIP archive submission for the IPP26 project.
# Usage: ./is_archive_ok.sh <archive.zip>

set -euo pipefail

# ---------------------------------------------------------------------------
# Color / output helpers
# ---------------------------------------------------------------------------
if [[ -t 1 && "${NO_COLOR:-}" == "" ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' NC=''
fi

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

pass_msg() { echo -e "${GREEN}[PASS]${NC} $*"; ((PASS_COUNT++)) || true; }
fail_msg() { echo -e "${RED}[FAIL]${NC} $*"; ((FAIL_COUNT++)) || true; }
warn_msg() { echo -e "${YELLOW}[WARN]${NC} $*"; ((WARN_COUNT++)) || true; }
info_msg() { echo -e "${CYAN}[INFO]${NC} $*"; }
section() {
    echo ""
    echo -e "${BOLD}━━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
WORK_DIR=""
ARCHIVE_ROOT=""
CONTAINER_FILE=""
INT_LANG=""
TESTER_LANG=""
DOCKER_TAG=""
DOCKER_AVAILABLE=false
CONTAINER_ENGINE="docker"  # or "podman", detected from Containerfile first line

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
cleanup() {
    if [[ "${DOCKER_AVAILABLE}" == "true" && -n "${DOCKER_TAG}" ]]; then
        for suffix in check build build-test runtime test; do
            "${CONTAINER_ENGINE}" rmi "${DOCKER_TAG}:${suffix}" --force 2>/dev/null || true
        done
    fi
    if [[ -n "${WORK_DIR}" && -d "${WORK_DIR}" ]]; then
        rm -rf "${WORK_DIR}"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 0. Argument validation and extraction
# ---------------------------------------------------------------------------
validate_and_extract() {
    section "Argument & Archive Validation"

    if [[ $# -ne 1 ]]; then
        echo "Usage: $0 <archive.zip>" >&2
        exit 2
    fi

    local zip_path="$1"

    if [[ ! -f "${zip_path}" ]]; then
        echo -e "${RED}ERROR:${NC} File not found: ${zip_path}" >&2
        exit 2
    fi

    if [[ ! -r "${zip_path}" ]]; then
        echo -e "${RED}ERROR:${NC} File is not readable: ${zip_path}" >&2
        exit 2
    fi

    local lower
    lower=$(echo "${zip_path}" | tr '[:upper:]' '[:lower:]')
    if [[ "${lower}" != *.zip ]]; then
        fail_msg "Archive filename does not have a .zip extension: ${zip_path}"
    fi

    local mime
    mime=$(file --mime-type -b "${zip_path}" 2>/dev/null || echo "unknown")
    if [[ "${mime}" != "application/zip" ]]; then
        fail_msg "File does not appear to be a ZIP archive (MIME type: ${mime})"
        # Still try to extract — maybe 'file' is wrong.
    else
        pass_msg "File is a valid ZIP archive"
    fi

    local size_bytes
    size_bytes=$(stat -c '%s' "${zip_path}" 2>/dev/null || stat -f '%z' "${zip_path}" 2>/dev/null || echo 0)
    local limit_bytes=$(( 5 * 1024 * 1024 ))
    if [[ ${size_bytes} -le ${limit_bytes} ]]; then
        pass_msg "Archive size is $(( size_bytes / 1024 )) KiB (limit: 5 MiB)"
    else
        fail_msg "Archive size is $(( size_bytes / 1024 )) KiB — exceeds the 5 MiB limit"
    fi

    WORK_DIR=$(mktemp -d /tmp/ipp26_check.XXXXXX)

    if ! unzip -q "${zip_path}" -d "${WORK_DIR}" 2>/tmp/ipp26_unzip_err.log; then
        fail_msg "Failed to extract archive. unzip output:"
        cat /tmp/ipp26_unzip_err.log
        exit 1
    fi
    pass_msg "Archive extracted successfully"

    # Derive a Docker tag from the archive filename (sanitized)
    local basename
    basename=$(basename "${zip_path}" .zip)
    DOCKER_TAG="ipp26check-$(echo "${basename}" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')"
    info_msg "Docker tag prefix: ${DOCKER_TAG}"

    ARCHIVE_ROOT="${WORK_DIR}"
}

# ---------------------------------------------------------------------------
# 1. Archive structure check
# ---------------------------------------------------------------------------
check_archive_structure() {
    section "Archive Structure"

    # Detect if the archive wrapped everything in a single subdirectory
    local top_entries
    top_entries=$(ls -A "${WORK_DIR}")
    local top_count
    top_count=$(echo "${top_entries}" | grep -c '.' || true)

    if [[ ${top_count} -eq 1 ]]; then
        local single="${WORK_DIR}/${top_entries}"
        if [[ -d "${single}" ]]; then
            # Check if this single dir contains int/ or tester/
            if [[ -d "${single}/int" || -d "${single}/tester" ]]; then
                fail_msg "Archive wraps all contents inside a subdirectory '${top_entries}/'. The archive root must directly contain int/ and tester/."
                # We can still analyse the structure for the user — use the subdir as root for remaining checks
                ARCHIVE_ROOT="${single}"
                info_msg "Continuing checks inside '${top_entries}/' for informational purposes."
            fi
        fi
    fi

    local has_int=false has_tester=false container_count=0 doc_count=0

    while IFS= read -r -d '' entry; do
        local name
        name=$(basename "${entry}")
        local relpath="${entry#"${ARCHIVE_ROOT}/"}"

        if [[ -d "${entry}" && "${name}" == "int" ]]; then
            has_int=true
            pass_msg "Found required directory: int/"
        elif [[ -d "${entry}" && "${name}" == "tester" ]]; then
            has_tester=true
            pass_msg "Found required directory: tester/"
        elif [[ -f "${entry}" && ( "${name}" == "Containerfile" || "${name}" == "Dockerfile" ) ]]; then
            ((container_count++)) || true
            CONTAINER_FILE="${name}"
            pass_msg "Found container definition: ${name}"
        elif [[ -f "${entry}" && ( "${name}" == "dokumentace.md" || "${name}" == "dokumentace.pdf" ) ]]; then
            ((doc_count++)) || true
            info_msg "Found documentation file: ${name}"
        elif [[ -f "${entry}" && ( "${name}" == ai-*.md || "${name}" == ai-*.pdf ) ]]; then
            info_msg "Found AI usage file: ${name}"
        else
            warn_msg "Unexpected entry at archive root: ${relpath} (this is OKAY but please mention the need for this file here in the docs)"
        fi
    done < <(find "${ARCHIVE_ROOT}" -maxdepth 1 -mindepth 1 -print0 | sort -z)

    [[ "${has_int}" == "true" ]] || fail_msg "Required directory 'int/' not found in archive root"
    [[ "${has_tester}" == "true" ]] || fail_msg "Required directory 'tester/' not found in archive root"

    if [[ ${container_count} -eq 0 ]]; then
        fail_msg "No Containerfile or Dockerfile found in archive root"
    elif [[ ${container_count} -gt 1 ]]; then
        fail_msg "Both Containerfile and Dockerfile are present — only one is allowed"
        # Prefer Containerfile for further analysis
        [[ -f "${ARCHIVE_ROOT}/Containerfile" ]] && CONTAINER_FILE="Containerfile" || CONTAINER_FILE="Dockerfile"
    else
        pass_msg "Exactly one container definition file present"
    fi

    if [[ ${doc_count} -gt 1 ]]; then
        warn_msg "Both dokumentace.md and dokumentace.pdf found — only PDF will be graded"
    fi

    # Check int/ and tester/ are not empty
    if [[ "${has_int}" == "true" ]]; then
        local int_count
        int_count=$(find "${ARCHIVE_ROOT}/int" -mindepth 1 -maxdepth 1 | wc -l)
        if [[ ${int_count} -eq 0 ]]; then
            fail_msg "Directory int/ is empty"
        else
            pass_msg "Directory int/ is non-empty"
        fi
    fi

    if [[ "${has_tester}" == "true" ]]; then
        local tester_count
        tester_count=$(find "${ARCHIVE_ROOT}/tester" -mindepth 1 -maxdepth 1 | wc -l)
        if [[ ${tester_count} -eq 0 ]]; then
            fail_msg "Directory tester/ is empty"
        else
            pass_msg "Directory tester/ is non-empty"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 2. Forbidden content check
# ---------------------------------------------------------------------------
check_forbidden_content() {
    section "Forbidden Content"

    local found_any=false

    # Hidden files and directories
    while IFS= read -r -d '' item; do
        local rel="${item#"${ARCHIVE_ROOT}/"}"
        fail_msg "Hidden file/directory found: ${rel}"
        found_any=true
    done < <(find "${ARCHIVE_ROOT}" -mindepth 1 \( -name '.*' ! -name '.gitignore' \) -print0 2>/dev/null)

    # __MACOSX
    while IFS= read -r -d '' item; do
        local rel="${item#"${ARCHIVE_ROOT}/"}"
        fail_msg "macOS artifact directory found: ${rel}"
        found_any=true
    done < <(find "${ARCHIVE_ROOT}" -type d -name '__MACOSX' -print0 2>/dev/null)

    # node_modules
    while IFS= read -r -d '' item; do
        local rel="${item#"${ARCHIVE_ROOT}/"}"
        fail_msg "node_modules directory found: ${rel}"
        found_any=true
    done < <(find "${ARCHIVE_ROOT}" -type d -name 'node_modules' -print0 2>/dev/null)

    # vendor (Composer / PHP)
    while IFS= read -r -d '' item; do
        local rel="${item#"${ARCHIVE_ROOT}/"}"
        fail_msg "Composer vendor directory found: ${rel}"
        found_any=true
    done < <(find "${ARCHIVE_ROOT}" -type d -name 'vendor' -print0 2>/dev/null)

    # __pycache__
    while IFS= read -r -d '' item; do
        local rel="${item#"${ARCHIVE_ROOT}/"}"
        fail_msg "Python cache directory found: ${rel}"
        found_any=true
    done < <(find "${ARCHIVE_ROOT}" -type d -name '__pycache__' -print0 2>/dev/null)

    # Python virtual environments (directories containing pyvenv.cfg)
    while IFS= read -r -d '' cfg; do
        local venv_dir
        venv_dir=$(dirname "${cfg}")
        local rel="${venv_dir#"${ARCHIVE_ROOT}/"}"
        fail_msg "Python virtual environment found: ${rel}/"
        found_any=true
    done < <(find "${ARCHIVE_ROOT}" -name 'pyvenv.cfg' -print0 2>/dev/null)

    # dist/ (compiled TS artifacts)
    while IFS= read -r -d '' item; do
        local rel="${item#"${ARCHIVE_ROOT}/"}"
        fail_msg "Compiled artifact directory 'dist/' found: ${rel}"
        found_any=true
    done < <(find "${ARCHIVE_ROOT}" -type d -name 'dist' -print0 2>/dev/null)

    # Compiled artifact extensions
    local bad_exts=("*.o" "*.so" "*.dll" "*.exe" "*.class" "*.pyc" "*.pyo")
    for pattern in "${bad_exts[@]}"; do
        while IFS= read -r -d '' item; do
            local rel="${item#"${ARCHIVE_ROOT}/"}"
            fail_msg "Compiled artifact found: ${rel}"
            found_any=true
        done < <(find "${ARCHIVE_ROOT}" -name "${pattern}" -print0 2>/dev/null)
    done

    # Binary executables (skip scripts — check for ELF/Mach-O/PE binaries via file(1))
    while IFS= read -r -d '' item; do
        local mime
        mime=$(file --mime-type -b "${item}" 2>/dev/null || echo "unknown")
        case "${mime}" in
            application/x-executable|application/x-pie-executable|\
            application/x-sharedlib|application/x-mach-binary|\
            application/x-mach-o-executable)
                local rel="${item#"${ARCHIVE_ROOT}/"}"
                fail_msg "Binary executable found: ${rel} (MIME: ${mime})"
                found_any=true
                ;;
        esac
    done < <(find "${ARCHIVE_ROOT}" -type f -print0 2>/dev/null)

    [[ "${found_any}" == "true" ]] || pass_msg "No forbidden content found"
}

# ---------------------------------------------------------------------------
# 3. Filename character check
# ---------------------------------------------------------------------------
check_filename_chars() {
    section "Filename Characters"

    local found_bad=false

    while IFS= read -r -d '' item; do
        local name
        name=$(basename "${item}")
        # Skip the archive root itself
        [[ "${item}" == "${ARCHIVE_ROOT}" ]] && continue

        if [[ "${name}" =~ [^A-Za-z0-9._-] ]]; then
            local rel="${item#"${ARCHIVE_ROOT}/"}"
            fail_msg "Forbidden characters in filename: '${rel}'"
            found_bad=true
        fi
    done < <(find "${ARCHIVE_ROOT}" -mindepth 1 -print0 | sort -z)

    [[ "${found_bad}" == "true" ]] || pass_msg "All filenames use only allowed characters"
}

# ---------------------------------------------------------------------------
# 4. Language detection
# ---------------------------------------------------------------------------
detect_languages() {
    section "Language Detection"

    detect_lang_for() {
        local dir="$1"
        local lang=""
        local hits=0

        if [[ -f "${dir}/pyproject.toml" || -f "${dir}/requirements.txt" ]]; then
            lang="python"; ((hits++)) || true
        fi
        if [[ -f "${dir}/package.json" && -f "${dir}/tsconfig.json" ]]; then
            lang="typescript"; ((hits++)) || true
        fi
        if [[ -f "${dir}/composer.json" ]]; then
            lang="php"; ((hits++)) || true
        fi

        if [[ ${hits} -eq 0 ]]; then
            echo "unknown"
        elif [[ ${hits} -gt 1 ]]; then
            echo "ambiguous"
        else
            echo "${lang}"
        fi
    }

    if [[ -d "${ARCHIVE_ROOT}/int" ]]; then
        INT_LANG=$(detect_lang_for "${ARCHIVE_ROOT}/int")
        if [[ "${INT_LANG}" == "unknown" ]]; then
            fail_msg "Cannot detect language for int/ (no pyproject.toml/requirements.txt, package.json+tsconfig.json, or composer.json)"
        elif [[ "${INT_LANG}" == "ambiguous" ]]; then
            warn_msg "Multiple language indicators found in int/ — unable to reliably determine language"
            INT_LANG="unknown"
        else
            pass_msg "Interpreter language: ${INT_LANG}"
        fi
    fi

    if [[ -d "${ARCHIVE_ROOT}/tester" ]]; then
        TESTER_LANG=$(detect_lang_for "${ARCHIVE_ROOT}/tester")
        if [[ "${TESTER_LANG}" == "unknown" ]]; then
            fail_msg "Cannot detect language for tester/ (no pyproject.toml/requirements.txt, package.json+tsconfig.json, or composer.json)"
        elif [[ "${TESTER_LANG}" == "ambiguous" ]]; then
            warn_msg "Multiple language indicators found in tester/ — unable to reliably determine language"
            TESTER_LANG="unknown"
        else
            pass_msg "Tester language: ${TESTER_LANG}"
        fi
    fi

    if [[ -n "${INT_LANG}" && "${INT_LANG}" != "unknown" && \
          -n "${TESTER_LANG}" && "${TESTER_LANG}" != "unknown" ]]; then
        if [[ "${INT_LANG}" == "${TESTER_LANG}" ]]; then
            fail_msg "Both int/ and tester/ use the same language (${INT_LANG}). The assignment requires two different languages."
        else
            pass_msg "Two different languages used: int/${INT_LANG}, tester/${TESTER_LANG}"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 4b. Python input_model.py search_mode check
# ---------------------------------------------------------------------------
check_python_input_model() {
    [[ "${INT_LANG}" == "python" ]] || return 0

    section "Python input_model.py: search_mode attributes"
    info_msg "This checks if the fix from template commit 64b94c15 is applied"

    # The file may live at a non-standard path, so search under int/
    local model_file
    model_file=$(find "${ARCHIVE_ROOT}/int" -type f -name "input_model.py" | head -n1)

    if [[ -z "${model_file}" ]]; then
        fail_msg "input_model.py not found anywhere under int/"
        return
    fi

    local rel="${model_file#"${ARCHIVE_ROOT}/"}"
    info_msg "Found: ${rel}"

    for cls in Send Assign Block; do
        if grep -qP "^class ${cls}\b.*\bsearch_mode\b" "${model_file}" 2>/dev/null || \
           grep -qE "^class ${cls}[^:]*search_mode" "${model_file}" 2>/dev/null; then
            pass_msg "class ${cls} has search_mode attribute"
        else
            fail_msg "class ${cls} is missing search_mode attribute (see commit 64b94c15)"
        fi
    done
}

# ---------------------------------------------------------------------------
# 4c. TypeScript input_model.ts htmlEntities check
# ---------------------------------------------------------------------------
check_ts_input_model() {
    [[ "${INT_LANG}" == "typescript" ]] || return 0

    section "TypeScript input_model.ts: htmlEntities option"
    info_msg "This checks if the fix from template commit 8e1fc87 is applied"

    local model_file
    model_file=$(find "${ARCHIVE_ROOT}/int" -type f -name "input_model.ts" | head -n1)

    if [[ -z "${model_file}" ]]; then
        fail_msg "input_model.ts not found anywhere under int/"
        return
    fi

    local rel="${model_file#"${ARCHIVE_ROOT}/"}"
    info_msg "Found: ${rel}"

    if grep -qE "htmlEntities\s*:\s*true" "${model_file}" 2>/dev/null; then
        pass_msg "XMLParser options contain htmlEntities: true"
    else
        fail_msg "XMLParser options are missing htmlEntities: true (see commit 8e1fc87)"
    fi
}

# ---------------------------------------------------------------------------
# 5. Containerfile stages check
# ---------------------------------------------------------------------------
check_containerfile_stages() {
    section "Containerfile Stages"

    [[ -n "${CONTAINER_FILE}" ]] || { warn_msg "No container file found — skipping stage analysis"; return; }

    local cfile="${ARCHIVE_ROOT}/${CONTAINER_FILE}"
    [[ -f "${cfile}" ]] || { fail_msg "Container file not found: ${CONTAINER_FILE}"; return; }

    # Check for ### podman on first line — determines which container engine to use
    local first_line
    first_line=$(head -n1 "${cfile}")
    if [[ "${first_line}" == "### podman"* ]]; then
        CONTAINER_ENGINE="podman"
        info_msg "Podman build mode requested (### podman on line 1) — will use podman"
    else
        CONTAINER_ENGINE="docker"
        info_msg "No '### podman' on line 1 — will use docker"
    fi

    # Parse stage names and their FROM lines
    # Associate array: stage_name -> FROM line content
    declare -A stage_from
    declare -A stage_has_entrypoint
    declare -a stage_order=()
    local current_stage=""

    while IFS= read -r line || [ -n "$line" ]; do
        # Match: FROM <image> AS <name>  (case-insensitive AS)
        if [[ "${line}" =~ ^[[:space:]]*[Ff][Rr][Oo][Mm][[:space:]]+(.+)[[:space:]]+[Aa][Ss][[:space:]]+([A-Za-z0-9_-]+) ]]; then
            current_stage="${BASH_REMATCH[2]}"
            stage_from["${current_stage}"]="${line}"
            stage_order+=("${current_stage}")
            stage_has_entrypoint["${current_stage}"]="false"
        elif [[ -n "${current_stage}" && "${line}" =~ ^[[:space:]]*[Ee][Nn][Tt][Rr][Yy][Pp][Oo][Ii][Nn][Tt] ]]; then
            stage_has_entrypoint["${current_stage}"]="true"
        fi
    done < "${cfile}"

    if [[ ${#stage_order[@]} -eq 0 ]]; then
        fail_msg "No named build stages (FROM ... AS <name>) found in ${CONTAINER_FILE}"
        return
    fi

    info_msg "Stages found: ${stage_order[*]}"

    # Required stages
    local required_stages=("check" "runtime" "test")
    if [[ "${INT_LANG}" == "typescript" ]]; then
        required_stages+=("build")
    fi
    if [[ "${TESTER_LANG}" == "typescript" ]]; then
        required_stages+=("build-test")
    fi

    for stage in "${required_stages[@]}"; do
        if [[ -n "${stage_from[${stage}]+_}" ]]; then
            pass_msg "Required stage '${stage}' found"
        else
            fail_msg "Required stage '${stage}' not found in ${CONTAINER_FILE}"
        fi
    done

    # Check: test stage must derive from runtime
    if [[ -n "${stage_from[test]+_}" ]]; then
        local test_from="${stage_from[test]}"
        if echo "${test_from}" | grep -qi 'runtime'; then
            pass_msg "Stage 'test' derives from 'runtime'"
        else
            fail_msg "Stage 'test' does not appear to derive from 'runtime' (FROM line: ${test_from})"
        fi
    fi

    # Check: check stage ENTRYPOINT must be bash
    if [[ -n "${stage_from[check]+_}" ]]; then
        if [[ "${stage_has_entrypoint[check]}" == "true" ]]; then
            # Verify it references bash
            local bash_ep
            bash_ep=$(grep -i 'ENTRYPOINT' "${cfile}" | head -n1 || true)
            # We need the ENTRYPOINT within the check stage specifically
            local in_check=false found_bash=false
            while IFS= read -r line; do
                if [[ "${line}" =~ ^[[:space:]]*[Ff][Rr][Oo][Mm].*[Aa][Ss][[:space:]]*check ]]; then
                    in_check=true
                elif [[ "${line}" =~ ^[[:space:]]*[Ff][Rr][Oo][Mm].*[Aa][Ss][[:space:]]*[A-Za-z0-9_-]+ && "${in_check}" == "true" ]]; then
                    # Entered a new stage — stop checking
                    in_check=false
                fi
                if [[ "${in_check}" == "true" && "${line}" =~ ^[[:space:]]*[Ee][Nn][Tt][Rr][Yy][Pp][Oo][Ii][Nn][Tt] ]]; then
                    if echo "${line}" | grep -q 'bash'; then
                        found_bash=true
                    fi
                fi
            done < "${cfile}"
            if [[ "${found_bash}" == "true" ]]; then
                pass_msg "Stage 'check' ENTRYPOINT uses bash"
            else
                warn_msg "Stage 'check' ENTRYPOINT does not reference bash (this is OKAY if this script later says that the necessary tools are executable)"
            fi
        else
            warn_msg "Stage 'check' has no ENTRYPOINT directive (usually should be set to bash)"
        fi
    fi

    # Check: runtime has ENTRYPOINT
    if [[ -n "${stage_from[runtime]+_}" ]]; then
        if [[ "${stage_has_entrypoint[runtime]}" == "true" ]]; then
            pass_msg "Stage 'runtime' has ENTRYPOINT"
        else
            fail_msg "Stage 'runtime' has no ENTRYPOINT directive"
        fi
    fi

    # Check: test has ENTRYPOINT
    if [[ -n "${stage_from[test]+_}" ]]; then
        if [[ "${stage_has_entrypoint[test]}" == "true" ]]; then
            pass_msg "Stage 'test' has ENTRYPOINT"
        else
            fail_msg "Stage 'test' has no ENTRYPOINT directive"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Docker availability check (done once before Docker sections)
# ---------------------------------------------------------------------------
check_docker_available() {
    if ! command -v "${CONTAINER_ENGINE}" &>/dev/null; then
        warn_msg "${CONTAINER_ENGINE} not found in PATH — skipping all container build/test checks"
        DOCKER_AVAILABLE=false
        return
    fi
    if ! "${CONTAINER_ENGINE}" info &>/dev/null 2>&1; then
        warn_msg "${CONTAINER_ENGINE} daemon is not running or not accessible — skipping all container build/test checks"
        DOCKER_AVAILABLE=false
        return
    fi
    pass_msg "${CONTAINER_ENGINE} is available"
    DOCKER_AVAILABLE=true
}

# Run a container build with a timeout, saving output to a log file.
# If BUILD_OUTPUT=1 is set, output is also streamed to stdout in real time.
# On failure without BUILD_OUTPUT=1, the saved log is printed.
# Always cds into ARCHIVE_ROOT so that --file <name> and context "." both resolve there.
# Usage: docker_build <log_file> [build args...]  (do NOT include the context "." — appended automatically)
docker_build() {
    local log_file="$1"; shift
    local file_arg=()
    [[ -n "${CONTAINER_FILE}" && "${CONTAINER_FILE}" != "Dockerfile" ]] && file_arg=(--file "${CONTAINER_FILE}")
    local rc=0
    if [[ "${BUILD_OUTPUT:-0}" == "1" ]]; then
        (cd "${ARCHIVE_ROOT}" && timeout 300 "${CONTAINER_ENGINE}" build "${file_arg[@]}" "$@" .) 2>&1 | tee "${log_file}"
        rc=${PIPESTATUS[0]}
    else
        (cd "${ARCHIVE_ROOT}" && timeout 300 "${CONTAINER_ENGINE}" build "${file_arg[@]}" "$@" .) >"${log_file}" 2>&1
        rc=$?
    fi
    if [[ ${rc} -ne 0 && "${BUILD_OUTPUT:-0}" != "1" ]]; then
        echo "  Build output:"
        sed 's/^/    /' "${log_file}"
    fi
    return ${rc}
}

# Run a docker run with a timeout, capturing stdout+stderr to a log file.
# Usage: docker_run <log_file> [docker run args...]
docker_run() {
    local log_file="$1"; shift
    if timeout 60 "${CONTAINER_ENGINE}" run "$@" >"${log_file}" 2>&1; then
        return 0
    else
        local rc=$?
        echo "  Container output:"
        sed 's/^/    /' "${log_file}"
        return ${rc}
    fi
}

# ---------------------------------------------------------------------------
# 6. Build and test: check stage
# ---------------------------------------------------------------------------
build_and_test_check() {
    section "Docker: check stage"
    [[ "${DOCKER_AVAILABLE}" == "true" ]] || { warn_msg "Skipping (Docker unavailable)"; return; }
    [[ -n "${CONTAINER_FILE}" ]] || { warn_msg "Skipping (no container file)"; return; }

    info_msg "Note that this script does NOT check the output of the code quality tools, it only checks if they can be executed."

    local log="${WORK_DIR}/docker_check_build.log"
    info_msg "Building check stage..."
    if docker_build "${log}" --target check --tag "${DOCKER_TAG}:check"; then
        pass_msg "docker build --target check succeeded"
    else
        fail_msg "docker build --target check FAILED"
        return
    fi

    # Test tool executability inside the container
    local tools_log="${WORK_DIR}/docker_check_tools.log"

    test_tool_in_check() {
        local src_dir="$1"   # /src/int or /src/tester
        local tool="$2"       # e.g. ruff
        local run_log="${WORK_DIR}/tool_${tool}.log"
        if docker_run "${run_log}" --rm \
            -v "${ARCHIVE_ROOT}/int/:/src/int/" \
            -v "${ARCHIVE_ROOT}/tester/:/src/tester/" \
            "${DOCKER_TAG}:check" \
            -c "cd ${src_dir} && ./${tool} --version 2>/dev/null || ./${tool} --help 2>/dev/null || ./${tool} 2>/dev/null; exit 0"; then
            pass_msg "Tool '${tool}' is executable in container (${src_dir})"
        else
            fail_msg "Tool '${tool}' is NOT executable in container (${src_dir})"
        fi
    }

    local tools_for_int=()
    local tools_for_tester=()

    case "${INT_LANG}" in
        python)     tools_for_int=("ruff" "mypy") ;;
        typescript) tools_for_int=("eslint" "prettier") ;;
        php)        tools_for_int=("phpstan" "phpcs") ;;
    esac

    case "${TESTER_LANG}" in
        python)     tools_for_tester=("ruff" "mypy") ;;
        typescript) tools_for_tester=("eslint" "prettier") ;;
        php)        tools_for_tester=("phpstan" "phpcs") ;;
    esac

    for tool in "${tools_for_int[@]+"${tools_for_int[@]}"}"; do
        test_tool_in_check "/src/int" "${tool}"
    done
    for tool in "${tools_for_tester[@]+"${tools_for_tester[@]}"}"; do
        test_tool_in_check "/src/tester" "${tool}"
    done
}

# ---------------------------------------------------------------------------
# 7. Build and test: build stage (TypeScript only)
# ---------------------------------------------------------------------------
build_and_test_build() {
    local need_build=false need_build_test=false
    [[ "${INT_LANG}" == "typescript" ]] && need_build=true
    [[ "${TESTER_LANG}" == "typescript" ]] && need_build_test=true
    [[ "${need_build}" == "true" || "${need_build_test}" == "true" ]] || return 0

    section "Docker: build stage (TypeScript)"
    [[ "${DOCKER_AVAILABLE}" == "true" ]] || { warn_msg "Skipping (Docker unavailable)"; return; }

    # --file is relative to CWD; we cd into ARCHIVE_ROOT so it equals the build context
    local file_arg=()
    [[ "${CONTAINER_FILE}" != "Dockerfile" ]] && file_arg=(--file "${CONTAINER_FILE}")

    if [[ "${need_build}" == "true" ]]; then
        info_msg "Building 'build' stage (TypeScript interpreter)..."
        local log="${WORK_DIR}/docker_build_int.log"
        if (cd "${ARCHIVE_ROOT}" && timeout 300 "${CONTAINER_ENGINE}" build "${file_arg[@]}" --target build --progress plain .) 2>"${log}"; then
            pass_msg "docker build --target build succeeded"
            if grep -qi 'error TS' "${log}" 2>/dev/null; then
                warn_msg "TypeScript compiler reported errors in build stage (see below)"
                grep -i 'error TS' "${log}" | sed 's/^/    /' || true
            fi
        else
            fail_msg "docker build --target build FAILED"
            cat "${log}" | sed 's/^/    /' || true
        fi
    fi

    if [[ "${need_build_test}" == "true" ]]; then
        info_msg "Building 'build-test' stage (TypeScript tester)..."
        local log="${WORK_DIR}/docker_build_tester.log"
        if (cd "${ARCHIVE_ROOT}" && timeout 300 "${CONTAINER_ENGINE}" build "${file_arg[@]}" --target build-test --progress plain .) 2>"${log}"; then
            pass_msg "docker build --target build-test succeeded"
            if grep -qi 'error TS' "${log}" 2>/dev/null; then
                warn_msg "TypeScript compiler reported errors in build-test stage"
                grep -i 'error TS' "${log}" | sed 's/^/    /' || true
            fi
        else
            fail_msg "docker build --target build-test FAILED"
            cat "${log}" | sed 's/^/    /' || true
        fi
    fi
}

# ---------------------------------------------------------------------------
# 8. Build and test: runtime stage
# ---------------------------------------------------------------------------
build_and_test_runtime() {
    section "Docker: runtime stage"
    [[ "${DOCKER_AVAILABLE}" == "true" ]] || { warn_msg "Skipping (Docker unavailable)"; return; }
    [[ -n "${CONTAINER_FILE}" ]] || { warn_msg "Skipping (no container file)"; return; }

    local log="${WORK_DIR}/docker_runtime_build.log"
    info_msg "Building runtime stage..."
    if docker_build "${log}" --target runtime --tag "${DOCKER_TAG}:runtime"; then
        pass_msg "docker build --target runtime succeeded"
    else
        fail_msg "docker build --target runtime FAILED"
        return
    fi

    # Test --help
    local help_log="${WORK_DIR}/runtime_help.log"
    info_msg "Testing interpreter --help..."
    local help_rc=0
    docker_run "${help_log}" --rm "${DOCKER_TAG}:runtime" --help || help_rc=$?
    if [[ ${help_rc} -eq 0 || ${help_rc} -eq 10 ]]; then
        pass_msg "Interpreter responds to --help (exit ${help_rc})"
    else
        warn_msg "Interpreter --help returned unexpected exit code ${help_rc}"
        cat "${help_log}" | sed 's/^/    /' || true
    fi

    # Test with a minimal SOL-XML program
    local prog_dir="${WORK_DIR}/minimal_program"
    mkdir -p "${prog_dir}"
    cat > "${prog_dir}/program.solxml" << 'SOLXML'
<?xml version="1.0" encoding="UTF-8"?>
<program language="SOL26">
  <class name="Main" parent="Object">
    <method selector="run">
      <block arity="0">
      </block>
    </method>
  </class>
</program>
SOLXML

    local run_log="${WORK_DIR}/runtime_run.log"
    info_msg "Testing interpreter with minimal SOL-XML program..."
    if docker_run "${run_log}" --rm \
        -v "${prog_dir}:/tmp/soltest/" \
        "${DOCKER_TAG}:runtime" \
        --source /tmp/soltest/program.solxml; then
        pass_msg "Interpreter ran minimal program successfully (exit 0)"
    else
        local rc=$?
        # Exit code 0 is expected for a trivial program; anything else is a failure
        fail_msg "Interpreter returned non-zero exit code (${rc}) for minimal program"
    fi
}

# ---------------------------------------------------------------------------
# 9. Build and test: test stage
# ---------------------------------------------------------------------------
build_and_test_test() {
    section "Docker: test stage"
    [[ "${DOCKER_AVAILABLE}" == "true" ]] || { warn_msg "Skipping (Docker unavailable)"; return; }
    [[ -n "${CONTAINER_FILE}" ]] || { warn_msg "Skipping (no container file)"; return; }

    local log="${WORK_DIR}/docker_test_build.log"
    info_msg "Building test stage..."
    if docker_build "${log}" --target test --tag "${DOCKER_TAG}:test"; then
        pass_msg "docker build --target test succeeded"
    else
        fail_msg "docker build --target test FAILED"
        return
    fi

    # Test --help
    local help_log="${WORK_DIR}/test_help.log"
    info_msg "Testing tester --help..."
    if docker_run "${help_log}" --rm "${DOCKER_TAG}:test" --help; then
        pass_msg "Tester responds to --help (exit 0)"
    else
        warn_msg "Tester --help returned non-zero exit code"
        cat "${help_log}" | sed 's/^/    /' || true
    fi

    # Test with an empty test directory
    local empty_tests="${WORK_DIR}/empty_tests"
    mkdir -p "${empty_tests}"
    local run_log="${WORK_DIR}/test_run.log"
    info_msg "Testing tester with empty test directory..."
    if docker_run "${run_log}" --rm \
        -v "${empty_tests}:/tmp/ipp26tests/" \
        "${DOCKER_TAG}:test" \
        /tmp/ipp26tests; then
        pass_msg "Tester ran with empty directory (exit 0)"
    else
        local rc=$?
        # Exit 1 means bad test directory, which is acceptable for an empty dir with some testers
        if [[ ${rc} -eq 1 ]]; then
            warn_msg "Tester exited with code 1 for empty directory (may be acceptable)"
            cat "${run_log}" | sed 's/^/    /' || true
        else
            fail_msg "Tester returned unexpected exit code ${rc} for empty directory"
            cat "${run_log}" | sed 's/^/    /' || true
        fi
    fi

    # Test with a combined SOL26 test (SOL26 source -> sol2xml -> interpreter)
    local combined_dir="${WORK_DIR}/combined_test"
    mkdir -p "${combined_dir}"
    # Write a minimal combined .test file (SOL26 source, not XML)
    printf '+++ CHECK\n*** Minimal combined test\n!C! 0\n!I! 0\n>>> 1\n\nclass Main : Object {\n  run [ | ]\n}\n' \
        > "${combined_dir}/minimal.test"
    local combined_log="${WORK_DIR}/test_combined.log"
    info_msg "Testing tester with a combined SOL26 test case (full pipeline: sol2xml + interpreter)..."
    local combined_rc=0
    docker_run "${combined_log}" --rm \
        -v "${combined_dir}:/tmp/ipp26tests/" \
        "${DOCKER_TAG}:test" \
        -o /tmp/ipp26tests/report.json \
        /tmp/ipp26tests || combined_rc=$?

    if [[ ${combined_rc} -ne 0 ]]; then
        warn_msg "Tester returned exit code ${combined_rc} for combined test run"
        cat "${combined_log}" | sed 's/^/    /' || true
    fi

    # Parse the JSON report to check if the test passed
    local report_file="${combined_dir}/report.json"
    if [[ ! -f "${report_file}" ]]; then
        warn_msg "Tester did not produce a report file at expected path"
    else
        local test_result=""
        if command -v python3 &>/dev/null; then
            test_result=$(python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get('results', {}).get('CHECK', {}).get('test_results', {}).get('minimal', {}).get('result', 'MISSING'))
except Exception as e:
    print('ERROR: ' + str(e))
" "${report_file}" 2>/dev/null || echo "ERROR")
        elif command -v jq &>/dev/null; then
            test_result=$(jq -r '.results.CHECK.test_results.minimal.result // "MISSING"' "${report_file}" 2>/dev/null || echo "ERROR")
        fi

        if [[ -z "${test_result}" ]]; then
            warn_msg "Neither python3 nor jq available to parse the report — printing raw JSON:"
            cat "${report_file}" | sed 's/^/    /' || true
        elif [[ "${test_result}" == "passed" ]]; then
            pass_msg "Combined test passed (tester successfully invoked sol2xml and interpreter)"
        elif [[ "${test_result}" == "MISSING" || "${test_result}" == "ERROR" ]]; then
            warn_msg "Could not read test result from report JSON (${test_result}) — printing raw JSON:"
            cat "${report_file}" | sed 's/^/    /' || true
        else
            warn_msg "Combined test result: '${test_result}' (expected 'passed')"
            # Print stderr from both stages to aid diagnosis
            if command -v python3 &>/dev/null; then
                python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
r = d.get('results', {}).get('CHECK', {}).get('test_results', {}).get('minimal', {})
for field in ('parser_stderr', 'interpreter_stderr', 'diff_output'):
    val = r.get(field)
    if val:
        print(field + ': ' + val)
" "${report_file}" 2>/dev/null | sed 's/^/    /' || true
            elif command -v jq &>/dev/null; then
                jq -r '
                    .results.CHECK.test_results.minimal |
                    to_entries[] |
                    select(.key | test("stderr|diff_output")) |
                    select(.value != null) |
                    "\(.key): \(.value)"
                ' "${report_file}" 2>/dev/null | sed 's/^/    /' || true
            fi
        fi
    fi
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary() {
    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}  SUMMARY${NC}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${GREEN}PASS: ${PASS_COUNT}${NC}"
    echo -e "  ${RED}FAIL: ${FAIL_COUNT}${NC}"
    echo -e "  ${YELLOW}WARN: ${WARN_COUNT}${NC}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    if [[ ${FAIL_COUNT} -eq 0 ]]; then
        echo -e "  ${GREEN}${BOLD}All hard checks passed.${NC}"
    else
        echo -e "  ${RED}${BOLD}${FAIL_COUNT} check(s) FAILED — submission likely has issues.${NC}"
    fi
    echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo -e "${BOLD}IPP26 Archive Submission Checker${NC}"
    echo "====================================================================================================="
    echo "Set an env variable BUILD_OUTPUT=1 to see the output of the Docker build process(es)."
    echo 'We recommend you to manually remove any project-related Docker images and/or run `docker image prune`'
    echo "before this script to observe whether your Docker build really works from a clean state."
    echo "====================================================================================================="

    validate_and_extract "$@"
    check_archive_structure
    check_forbidden_content
    check_filename_chars
    detect_languages
    check_python_input_model
    check_ts_input_model
    check_containerfile_stages

    section "Docker Availability"
    check_docker_available

    build_and_test_check
    build_and_test_build
    build_and_test_runtime
    build_and_test_test

    print_summary

    [[ ${FAIL_COUNT} -eq 0 ]]
}

main "$@"