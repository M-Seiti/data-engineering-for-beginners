# Lição 02 — Do dado bruto para uma tabela limpa

[🏠 Índice](README.md) · [⬅️ Lição 01](01-open-meteo-client.md) · [🇺🇸 English](../en/02-raw-to-staging.md) · [💻 Código](../../code/02-raw-to-staging/)

---

## O que você vai aprender

- [ ] Como ler o JSON bruto salvo na lição 01
- [ ] Como transformar listas paralelas numa tabela com uma linha por dia
- [ ] Como declarar e converter o tipo de cada coluna de forma explícita
- [ ] Como acrescentar colunas de contexto (local e horário da coleta)
- [ ] Como validar o conteúdo e parar o pipeline quando algo está errado
- [ ] Como salvar o resultado em Parquet, e por que Parquet em vez de CSV

## Antes de começar

**Rode a lição 01 primeiro.** Esta lição não chama a API. Ela lê o arquivo que a lição 01 salvou em `data/raw/open_meteo/`. É exatamente para isso que a camada raw existe: a transformação pode rodar, quebrar e rodar de novo sem gastar nenhuma requisição.

Instale as bibliotecas novas:

```bash
pip install pandas pyarrow
```

- **`pandas`** trabalha com tabelas (chamadas de *DataFrames*).
- **`pyarrow`** é o que o pandas usa por trás para gravar arquivos Parquet. Você nunca o importa, mas sem ele o `to_parquet` falha.

### Olhe o dado primeiro

O motivo mais comum para se perder numa transformação é não conhecer o formato do que está sendo transformado. Abra o JSON da lição 01. Ele tem esta forma:

```json
{
  "meta": { "collected_at": "2026-09-24T13:00:00+00:00", "...": "..." },
  "body": {
    "latitude": -16.75,
    "longitude": -43.875,
    "daily": {
      "time":              ["2024-03-01", "2024-03-02", "2024-03-03"],
      "precipitation_sum": [0.0,          3.2,          null]
    }
  }
}
```

Duas coisas para reparar:

- Dentro de `daily` há **duas listas do mesmo tamanho**, e a posição liga uma à outra. A primeira data de `time` corresponde ao primeiro valor de `precipitation_sum`, e assim por diante. Isso se chama **listas paralelas**. O trabalho desta lição é transformá-las numa tabela com uma linha por dia.
- Pedimos a latitude `-16.72`, mas a API respondeu `-16.75`. O Open-Meteo trabalha com uma grade de pontos e devolve o mais próximo. Por isso guardamos as coordenadas **da resposta**, e não as que pedimos.

---

## Parte 1 — Bibliotecas e configurações

```python
import json
import logging

from datetime import date
from pathlib import Path

import pandas as pd
```

`json`, `logging`, `date` e `Path` você já conhece da lição 01. A novidade é o **`pandas`**, importado como `pd`. O `as pd` é só um nome mais curto; é uma convenção que quase todo mundo usa.

> 💡 A biblioteca padrão do Python vem primeiro, e as bibliotecas instaladas (`pandas`) vêm por último, separadas por uma linha em branco. Essa ordem vem da PEP 8 e facilita ver o que precisa ser instalado.

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("transform")
```

A mesma configuração de log da lição 01, com outro nome de logger, para sabermos qual script escreveu cada mensagem.

```python
# Repository root: transform.py -> 02-raw-to-staging -> code -> root
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
```

A mesma pasta `data/` na raiz do repositório que a lição 01 usa. O `.parents[2]` sobe três níveis: do arquivo para a pasta dele, depois para `code/` e daí para a raiz. Como as duas lições apontam para o mesmo lugar, a lição 02 encontra o arquivo que a lição 01 salvou.

```python
FIXED_COLUMNS = ["date", "latitude", "longitude", "collected_at"]
```

As colunas que **sempre** existem na nossa tabela. Todas as outras serão variáveis meteorológicas, como `precipitation_sum`. Manter essa lista num lugar só permite que o código funcione com qualquer número de variáveis sem mudanças.

---

## Parte 2 — Lendo o arquivo raw

```python
# Reads the raw JSON saved by lesson 01
def read_raw(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
```

É o `raw_save` ao contrário:

- `path.read_text(encoding="utf-8")` lê o arquivo inteiro como texto.
- `json.loads(...)` transforma esse texto de volta em dicionário Python.

> 💡 `json.dumps` (com **s**) transforma dicionário em texto; `json.loads` transforma texto em dicionário. O **s** vem de *string*.

---

## Parte 3 — De listas paralelas para uma tabela

```python
# Turns the parallel lists into one row per day, plus context columns
def to_dataframe(raw: dict) -> pd.DataFrame:
    body = raw["body"]

    df = pd.DataFrame(body["daily"])
    df = df.rename(columns={"time": "date"})
```

- **`body = raw["body"]`** guarda a resposta da API numa variável curta, para não repetirmos `raw["body"]` em todo lugar.
- **`pd.DataFrame(body["daily"])`** faz quase todo o trabalho. Quando você passa ao pandas um **dicionário de listas**, **cada chave vira uma coluna** e cada posição das listas vira uma linha:

  ```
           time  precipitation_sum
  0  2024-03-01                0.0
  1  2024-03-02                3.2
  2  2024-03-03                NaN
  ```

  O `null` do JSON virou `NaN` (*Not a Number*), que é como o pandas representa um número vazio.
- **`df.rename(columns={"time": "date"})`** troca o nome da coluna `time` por `date`, que descreve melhor o conteúdo. O `rename` devolve uma tabela **nova**, por isso guardamos o resultado de volta em `df`.

> 💡 Se você pedir mais variáveis na lição 01 (por exemplo `"precipitation_sum,temperature_2m_max"`), o `daily` terá mais listas, e esta mesma linha criará mais colunas. Nada no código precisa mudar.

### Colunas de contexto

```python
    df["latitude"] = body["latitude"]
    df["longitude"] = body["longitude"]
    df["collected_at"] = raw["meta"]["collected_at"]
    return df
```

Quando você atribui um **valor único** a uma coluna, o pandas o repete em todas as linhas. Numa tabela de 7 linhas parece redundante, mas, quando você juntar dados de várias cidades e várias coletas numa tabela só, são essas colunas que dizem de onde veio cada linha.

Repare que `collected_at` vem do `meta`, a parte que a lição 01 escreveu sobre a própria requisição.

---

## Parte 4 — Declarando o schema

Neste ponto, a coluna `date` ainda é **texto**, não data. O pandas não adivinha isso por você, e é bom que não adivinhe: um palpite errado é pior do que nenhum palpite.

### Conferindo se as colunas existem

```python
# Converts every column to its declared type
def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(FIXED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
```

- `set(...)` transforma uma lista num **conjunto**: uma coleção sem itens repetidos e sem ordem.
- Subtrair dois conjuntos (`-`) devolve os itens que estão no primeiro e **não** estão no segundo. Então `missing` contém as colunas fixas que não vieram nos dados.
- Um conjunto vazio vale `False` num `if`, então o erro só é lançado quando falta alguma coisa.

Se você pensa em C, a mesma checagem com laços seria:

```python
missing = []
for col in FIXED_COLUMNS:
    if col not in df.columns:
        missing.append(col)
```

As duas versões fazem a mesma coisa. A versão com conjuntos é mais curta e é a que você vai encontrar na maior parte do código Python.

### Convertendo as datas

```python
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], format="%Y-%m-%d")
    out["collected_at"] = pd.to_datetime(out["collected_at"], utc=True)
```

- **`df.copy()`** cria uma cópia independente. Alteramos `out`, e o `df` original fica intacto. Alterar dados que outra parte do programa passou para a sua função é uma fonte comum de bugs difíceis de achar.
- **`pd.to_datetime(..., format="%Y-%m-%d")`** converte texto em data. O `format` diz exatamente como o texto está escrito: ano com quatro dígitos, mês, dia. Se uma data chegar em outro formato, a conversão **falha** em vez de adivinhar (`03/04` é 4 de março ou 3 de abril?).
- **`utc=True`** mantém o `collected_at` em UTC, o mesmo fuso que a lição 01 usou para escrevê-lo.

### Convertendo os números

```python
    numeric = [col for col in out.columns if col not in ("date", "collected_at")]
```

Isso é uma **list comprehension**: um jeito compacto de montar uma lista. Leia como "uma lista com cada `col` de `out.columns`, mantendo só as que não são `date` nem `collected_at`". A versão com laço é:

```python
numeric = []
for col in out.columns:
    if col not in ("date", "collected_at"):
        numeric.append(col)
```

O resultado são todas as colunas que devem ser número: `latitude`, `longitude` e todas as variáveis meteorológicas.

```python
    for col in numeric:
        # errors="raise": an invalid value stops the program instead of becoming empty
        out[col] = pd.to_numeric(out[col], errors="raise").astype("float64")
```

- **`pd.to_numeric(..., errors="raise")`** converte a coluna em números. Se algum valor não puder ser convertido (por exemplo, o texto `"muita"`), o programa **para** com erro. A alternativa, `errors="coerce"`, transformaria esse valor em `NaN` em silêncio, e você nunca saberia que o dado chegou quebrado.
- **`.astype("float64")`** garante que todas as colunas numéricas tenham o mesmo tipo: número decimal com 64 bits de precisão, o equivalente ao `double` do C.

### Ordenando as colunas

```python
    variables = [col for col in out.columns if col not in FIXED_COLUMNS]
    return out[FIXED_COLUMNS + variables]
```

`variables` são todas as colunas que não são fixas: as variáveis meteorológicas. `FIXED_COLUMNS + variables` junta as duas listas, e `out[...]` com uma lista de nomes devolve a tabela **com as colunas nessa ordem**. Colunas fixas primeiro, variáveis depois: todo arquivo do staging terá o mesmo formato.

---

## Parte 5 — Validando o conteúdo

O schema verifica a **forma** do dado: colunas e tipos. A validação verifica se o **conteúdo** faz sentido.

```python
# Checks the content; any problem stops the pipeline
def validate(df: pd.DataFrame, start: date, end: date) -> None:
    errors = []
```

Juntamos todos os problemas numa lista em vez de parar no primeiro. Se duas coisas estiverem erradas, a mensagem de erro mostra as duas, e você corrige tudo de uma vez.

### Regra 1: sem datas repetidas

```python
    if df["date"].duplicated().any():
        errors.append("repeated dates")
```

Dois métodos encadeados:

- **`.duplicated()`** devolve, para cada linha, `True` se aquela data já apareceu numa linha acima, e `False` caso contrário.
- **`.any()`** devolve `True` se **pelo menos um** valor for `True`.

Juntos: "existe alguma data repetida?". Na forma de laço:

```python
seen = set()
has_duplicates = False
for d in df["date"]:
    if d in seen:
        has_duplicates = True
    seen.add(d)
```

### Regra 2: nenhum dia faltando

```python
    expected_days = pd.date_range(start, end, freq="D")
    missing_days = expected_days.difference(df["date"])
    if len(missing_days) > 0:
        errors.append(f"missing days: {[d.date().isoformat() for d in missing_days]}")
```

- **`pd.date_range(start, end, freq="D")`** gera todos os dias que **deveriam** existir no período (`freq="D"` significa diário).
- **`.difference(...)`** devolve os dias que estão na lista esperada mas **não** estão nos dados. É a mesma ideia da subtração de conjuntos da Parte 4.
- A list comprehension dentro da mensagem transforma cada dia faltante num texto legível, como `2024-03-03`.

### Regra 3: chuva nunca negativa

```python
    if "precipitation_sum" in df.columns and (df["precipitation_sum"] < 0).any():
        errors.append("negative rain")
```

- `"precipitation_sum" in df.columns` verifica primeiro se a coluna existe. Se não existir, o Python nem avalia a segunda parte do `and`.
- `df["precipitation_sum"] < 0` compara **todas as linhas de uma vez** e devolve uma coluna de `True`/`False`. O `.any()` pergunta se alguma delas é `True`.

> 💡 Esse "operar na coluna inteira de uma vez" se chama **vetorização**. Ele substitui o laço `for` que você escreveria em C e, no pandas, é muito mais rápido.

### Parando o pipeline

```python
    if errors:
        raise ValueError("Validation failed: " + "; ".join(errors))
```

Uma lista vazia vale `False`, então isso só roda quando existe pelo menos um problema. O `"; ".join(errors)` cola todas as mensagens num texto só, separadas por `; `.

### Valores vazios: aviso, não erro

```python
    nulls = int(df.drop(columns=FIXED_COLUMNS).isna().sum().sum())
    if nulls:
        log.warning("%s empty values (the API had no data for them)", nulls)
```

Leia da esquerda para a direita:

1. `df.drop(columns=FIXED_COLUMNS)` mantém só as variáveis meteorológicas.
2. `.isna()` devolve `True` em cada célula vazia.
3. O primeiro `.sum()` conta os `True` **de cada coluna** (`True` vale 1).
4. O segundo `.sum()` soma as contagens de todas as colunas.
5. `int(...)` transforma o resultado num inteiro comum do Python.

Por que só um aviso? É normal uma API não ter medição para algum dia. Já um dia inteiro **sumido** da resposta é sinal de problema real. Decidir o que é "estranho, mas aceitável" e o que é "errado" é uma escolha que todo pipeline precisa fazer. Registre essa escolha no seu projeto.

---

## Parte 6 — Salvando em Parquet

```python
# Saves as Parquet, with the same atomic trick as raw_save
def save_staging(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    log.info("staging saved to %s (%s rows)", path, len(df))
```

A estrutura é a mesma do `raw_save` da lição 01: criar a pasta, gravar num arquivo temporário, renomear de forma atômica. Duas diferenças:

- **`df.to_parquet(tmp, index=False)`** grava a tabela no formato Parquet. O `index=False` evita salvar a numeração das linhas (0, 1, 2...), que não é dado de verdade.
- O log também mostra quantas linhas foram salvas: `len(df)` é o número de linhas da tabela.

### Por que Parquet e não CSV?

| | CSV | Parquet |
|---|---|---|
| Tipos | Perdidos: tudo volta como texto quando você lê de novo | Mantidos: datas continuam datas, números continuam números |
| Tamanho | Maior | Menor, porque é comprimido |
| Ler uma coluna só | Lê o arquivo inteiro | Lê só aquela coluna |
| Abre num editor de texto | Sim | Não |

A primeira linha é a mais importante. Se você salvar em CSV e ler de novo, `date` volta como texto, e você precisa declarar o schema tudo de novo. Com Parquet, os tipos que você declarou na Parte 4 viajam junto com os dados.

Esta é a **camada staging**: dado limpo, tipado e validado, pronto para as próximas etapas.

---

## Parte 7 — Rodando tudo

```python
if __name__ == "__main__":
    start, end = date(2024, 3, 1), date(2024, 3, 7)

    raw_path = DATA_DIR / "raw" / "open_meteo" / f"{start}_{end}.json"
    staging_path = DATA_DIR / "staging" / "open_meteo" / f"{start}_{end}.parquet"

    raw = read_raw(raw_path)
    df = to_dataframe(raw)
    df = enforce_schema(df)
    validate(df, start, end)
    save_staging(df, staging_path)

    print(df)
    print(df.dtypes)
```

- As datas precisam ser as mesmas usadas na lição 01, porque fazem parte do nome do arquivo raw.
- `raw_path` é onde a lição 01 salvou os dados; `staging_path` é onde esta lição vai salvar. Mesmo nome, camada e extensão diferentes.
- As cinco chamadas são os cinco passos da lição, em ordem: ler, montar a tabela, aplicar o schema, validar, salvar.
- `print(df.dtypes)` mostra o tipo de cada coluna, para você confirmar que o schema funcionou.

Rode com:

```bash
cd code/02-raw-to-staging
python transform.py
```

Você deve ver a tabela com 7 linhas e, embaixo, os tipos:

```
date                 datetime64[ns]
latitude                    float64
longitude                   float64
collected_at    datetime64[ns, UTC]
precipitation_sum           float64
```

Dependendo da versão do pandas, as datas podem aparecer como `datetime64[us]` em vez de `[ns]`. As duas são datas; só muda a precisão. Um arquivo novo vai aparecer em `data/staging/open_meteo/`.

---

## Código completo

> O mesmo código está em [`code/02-raw-to-staging/transform.py`](../../code/02-raw-to-staging/transform.py).

```python
import json
import logging

from datetime import date
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("transform")

# Repository root: transform.py -> 02-raw-to-staging -> code -> root
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

FIXED_COLUMNS = ["date", "latitude", "longitude", "collected_at"]


# Reads the raw JSON saved by lesson 01
def read_raw(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# Turns the parallel lists into one row per day, plus context columns
def to_dataframe(raw: dict) -> pd.DataFrame:
    body = raw["body"]

    df = pd.DataFrame(body["daily"])
    df = df.rename(columns={"time": "date"})

    df["latitude"] = body["latitude"]
    df["longitude"] = body["longitude"]
    df["collected_at"] = raw["meta"]["collected_at"]
    return df


# Converts every column to its declared type
def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(FIXED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], format="%Y-%m-%d")
    out["collected_at"] = pd.to_datetime(out["collected_at"], utc=True)

    numeric = [col for col in out.columns if col not in ("date", "collected_at")]
    for col in numeric:
        # errors="raise": an invalid value stops the program instead of becoming empty
        out[col] = pd.to_numeric(out[col], errors="raise").astype("float64")

    variables = [col for col in out.columns if col not in FIXED_COLUMNS]
    return out[FIXED_COLUMNS + variables]


# Checks the content; any problem stops the pipeline
def validate(df: pd.DataFrame, start: date, end: date) -> None:
    errors = []

    if df["date"].duplicated().any():
        errors.append("repeated dates")

    expected_days = pd.date_range(start, end, freq="D")
    missing_days = expected_days.difference(df["date"])
    if len(missing_days) > 0:
        errors.append(f"missing days: {[d.date().isoformat() for d in missing_days]}")

    if "precipitation_sum" in df.columns and (df["precipitation_sum"] < 0).any():
        errors.append("negative rain")

    if errors:
        raise ValueError("Validation failed: " + "; ".join(errors))

    nulls = int(df.drop(columns=FIXED_COLUMNS).isna().sum().sum())
    if nulls:
        log.warning("%s empty values (the API had no data for them)", nulls)


# Saves as Parquet, with the same atomic trick as raw_save
def save_staging(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    log.info("staging saved to %s (%s rows)", path, len(df))


if __name__ == "__main__":
    start, end = date(2024, 3, 1), date(2024, 3, 7)

    raw_path = DATA_DIR / "raw" / "open_meteo" / f"{start}_{end}.json"
    staging_path = DATA_DIR / "staging" / "open_meteo" / f"{start}_{end}.parquet"

    raw = read_raw(raw_path)
    df = to_dataframe(raw)
    df = enforce_schema(df)
    validate(df, start, end)
    save_staging(df, staging_path)

    print(df)
    print(df.dtypes)
```

---

## Exercícios

1. Abra o JSON raw, apague um dia das **duas** listas e rode o script. Qual regra falha?
2. Troque um valor de chuva pelo texto `"muita"` e rode de novo. Qual função para o programa, e por quê?
3. Salve o mesmo DataFrame em CSV com `df.to_csv("teste.csv", index=False)`. Compare o tamanho dos arquivos, depois leia os dois de volta com `pd.read_csv` e `pd.read_parquet` e compare os `dtypes`.
4. Peça `"precipitation_sum,temperature_2m_max"` na lição 01, rode as duas lições de novo e confira que a coluna nova aparece sem mudar este código.

---

[🏠 Índice](README.md) · [⬅️ Lição 01](01-open-meteo-client.md) · [🇺🇸 English](../en/02-raw-to-staging.md) · [💻 Código](../../code/02-raw-to-staging/)
