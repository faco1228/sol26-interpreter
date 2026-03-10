# Nástroj pro integrační testování – TypeScript

> [!NOTE]
> Platí zde všechny obecné instrukce pro řešení v jazyce TypeScript, které jsou uvedeny v `README.md` v nadřazeném adresáři.

Při implementaci nástroje pro integrační testování máte v zásadě volnou ruku. K dispozici máte předpřipravenou kostru s načítáním parametrů z příkazové řádky, kterou můžete libovolně upravit.

**Povinně** musíte využít modely definované v modulu `models.ts`. Zde najdete třídy, které reprezentují načtený test (`TestCaseDefinition`) i výstupní report (`TestReport`). Modely neměňte (pokud by to z nějakého důvodu pro vás bylo nezbytné, konzultujte to na fóru). Zejména z modelu `TestCaseDefinition` však můžete dědit ve vlastním modelu, který bude obsahovat další atributy.

## Spouštění v kontejneru a interakce s dalšími nástroji

Není specifikován konkrétní způsob, jakým váš testovací nástroj spustí překladač SOL2XML a váš 
interpret. Cesty k překladači a interpretu tedy v podstatě mohou být i napevno definované ve vašem 
kódu, ačkoliv to není považováno za vhodné řešení. Doporučujeme raději použít proměnné prostředí, 
konfigurační soubor nebo vlastní parametry příkazové řádky.

Povinně podporované parametry příkazové řádky jsou popsány v zadání.

## Návratové kódy

Testovací nástroj podporuje pouze následující chybové návratové kódy:
- 1: Zadaná cesta k adresáři s testy neexistuje nebo není adresářem.
- 2: Neplatné argumenty (např. chybějící povinné argumenty, neznámé argumenty atd.).

V nástroji jinak neexistuje žádný „očekávaný“ chybový stav. V případě neočekávaných chyb při
spouštění jednotlivých testů se záznam o této chybě projeví v reportu (vizte model `UnexecutedReason`),
ale testovací nástroj by měl i tak provést všechny testy a skončit s návratovým kódem 0.