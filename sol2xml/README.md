# Překladač SOL2XML

V tomto adresáři se nachází jednoduchý pythonový skript `sol_to_xml.py`. Ten slouží pro „překlad“
zdrojového kódu v lidsky čitelné formě jazyka SOL26 do formátu SOL-XML, který je vstupním formátem
pro váš interpret.

Nástroj lze spustit bez parametrů příkazové řádky, kdy čte kód SOL26 ze standardního vstupu, nebo 
je možné použít jediný parametr, kterým je cesta ke vstupnímu souboru s kódem SOL26. Cílové XML
je vždy tisknuto na standardní výstup.

```bash
python sol_to_xml.py <in_file.sol >out_file.xml  # 1. možnost
python sol_to_xml.py in_file.sol >out_file.xml  # 2. možnost
```

V případě neúspěchu (syntaktické chyby ve vstupu) je skript ukončen s návratovým kódem 1.

### Závislosti

Skript vyžaduje pro spuštění knihovny, které jsou definovány v souboru `requirements.txt`.
Více informací k nakládání s pythonovými projekty se závislostmi najdete v README souboru
pro pythonové projekty (`/python/README.md`).

### Validace podle schématu

V souboru `parser_output_schema.xsd` se nachází XSD schéma, které popisují formát SOL-XML,
tedy všechny validní SOL-XML soubory musí tomuto schématu odpovídat. Pokud je schéma
k dispozici (v pracovním adresáři, z něhož je skript spuštěn), bude automaticky provedena
validace výstupu. Ta by **měla vždy dopadnout dobře**. Pokud byste při experimentech
narazili na kód v jazyce SOL26, pro který překladač vypíše zprávu „Generated XML does 
not conform to the schema“ a skončí s návratovým kódem 2, **kontaktujte cvičícího**.
Znamená to, že je v překladači chyba, která není na vaší straně. :)

