ZIPNAME = xfackas00.zip
STAGING = .zip-staging

.PHONY: zip build clean stage

stage:
	rm -rf $(STAGING)
	mkdir -p $(STAGING)/int $(STAGING)/tester

	rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' \
	      --exclude='*.sol' --exclude='*.xml' \
	      int/ $(STAGING)/int/
	find $(STAGING)/int -type d -name '.mypy_cache' -exec rm -rf {} + 2>/dev/null || true
	find $(STAGING)/int -type d -name '.ruff_cache' -exec rm -rf {} + 2>/dev/null || true

	rsync -a --exclude='node_modules' --exclude='dist' \
	      tester/ $(STAGING)/tester/

	cp Containerfile $(STAGING)/

zip: stage
	rm -f $(ZIPNAME)
	cd $(STAGING) && zip -r ../$(ZIPNAME) .
	rm -rf $(STAGING)
	@echo "Created $(ZIPNAME)"

build: stage
	docker build --target runtime -t sol26-interpreter $(STAGING)
	rm -rf $(STAGING)

build-check: stage
	docker build --target check -t sol26-check $(STAGING)
	rm -rf $(STAGING)

build-test: stage
	docker build --target test -t sol26-test $(STAGING)
	rm -rf $(STAGING)

clean:
	rm -rf $(STAGING) $(ZIPNAME)
