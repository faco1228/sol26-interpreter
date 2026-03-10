# Nástroj pro integrační testování – Python

> [!NOTE]
> Platí zde všechny obecné instrukce pro řešení v jazyce Python, které jsou 
> uvedeny v [README.md](../README.md) v nadřazeném adresáři.

Při implementaci nástroje pro integrační testování máte v zásadě volnou ruku. K dispozici máte
předpřipravenou kostru s načítáním parametrů z příkazové řádky, kterou můžete libovolně upravit.

**Povinně** musíte využít modely definované v modulu `models.py`. Zde najdete třídy, které reprezentují
načtený test (`TestCaseDefinition`) i výstupní report (`TestReport`). Modely neměňte (pokud by to
z nějakého důvodu pro vás bylo nezbytné, konzultujte to na fóru). Zejména z modelu `TestCaseDefinition`
však můžete dědit ve vlastním modelu, který bude obsahovat další atributy.

## Spouštění v kontejneru a interakce s dalšími nástroji

Nástroj vyžaduje minimálně knihovnu `pydantic`, takže i zde je nutné využít nějakou formu správy
projektu a balíčků (viz obecné instrukce).

Není specifikován konkrétní způsob, jakým váš testovací nástroj spustí překladač SOL2XML a váš 
interpret. Cesty k překladači a interpretu tedy v podstatě mohou být i napevno definované ve vašem 
kódu, ačkoliv to není považováno za vhodné řešení. Doporučujeme raději použít proměnné prostředí, 
konfigurační soubor nebo vlastní parametry příkazové řádky.

Konkrétně v případě Pythonu je také **povoleno** překladač SOL2XML, který je implementovaný
jako pythonový skript, zaintegrovat přímo do kódu testovacího nástroje a využívat jej tedy v podstatě
jako knihovnu. Nezapomeňte toto řešení popsat v dokumentaci a v odevzdaném kódu jasně vyznačit, které
části jste vypracovali vy, a které jsou převzaty.

Povinně podporované parametry příkazové řádky jsou popsány v zadání.

## Návratové kódy

Testovací nástroj podporuje pouze následující chybové návratové kódy:
- 1: Zadaná cesta k adresáři s testy neexistuje nebo není adresářem.
- 2: Neplatné argumenty (např. chybějící povinné argumenty, neznámé argumenty, atd.).
     Poznámka: s tímto kódem automaticky ukončuje program knihovna `argparse`.

V nástroji jinak neexistuje žádný „očekávaný“ chybový stav. V případě neočekávaných chyb při
spouštění jednotlivých testů se záznam o této chybě projeví v reportu (vizte model `UnexecutedReason`),
ale testovací nástroj by měl i tak provést všechny testy a skončit s návratovým kódem 0.