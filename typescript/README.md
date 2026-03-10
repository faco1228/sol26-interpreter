# Šablony pro IPP projekt – TypeScript

## Nástroje pro kontrolu kvality kódu

V obou šablonách jsou pomocí souborů `eslint.config.mjs`, `prettier.config.mjs` a `tsconfig.json` nakonfigurovány 
nástroje ESLint, Prettier a TypeScript. Do konfigurace nástrojů **zakázáno zasahovat** (bude kontrolováno).
Můžete si však podle potřeby upravovat `package.json`.

Jakmile je prostředí nainstalováno (pomocí `npm install`), lze nástroje spustit z kořenového adresáře projektu pomocí 
`npm run lint` a `npm run format` (definováno v `package.json`). Doporučujeme oba nástroje spouštět **pravidelně** v průběhu
vývoje – jinak se chyby zvládnou velice rychle nahromadit. Pro různá IDE či editory kódu také existují rozšíření, která umí
alespoň částečně nástroje integrovat přímo do svých kontrol kódu

Doporučujeme využít nástroj [pre-commit](https://pre-commit.com/), který se integruje s gitem a při každém commitu 
automaticky spustí potřebné kontroly. V případě, že kontroly selžou, nedovolí (bez použití přepínače `--no-verify`) 
commit ani vytvořit. Příklad konfiguračního souboru bude doplněn.

### Povolené výjimky z automatických kontrol kvality

V odůvodněných případech může být ignorováno pravidlo ESLint `complexity`, které upozorňuje na příliš komplexní
funkce podle jisté metriky. V případě výskytu tohoto hlášení doporučujeme pořádně se zamyslet, zda opravdu nelze
kód napsat jinak. Pokud ne, obraťte se s žádostí o potvrzení na cvičicí (na fóru).

Pokud vám některá pravidla budou připadat příliš restriktivní, obraťte se na nás na fóru. V případě 
dobré argumentace se zde pak mohou objevit další povolené výjimky. Nástroje pro kontrolu kvality kódu 
nemusí mít vždycky pravdu.

## Správa projektu a závislostí

V šablonách je povinně využito prostředí Node.js + TypeScript. Závislosti jsou deklarované v `package.json`.

Příklad:

```bash
# nainstaluje závislosti
npm install
# přeloží TS kód
npm run build
# spustí přeložený skript
node dist/tester.js
```
