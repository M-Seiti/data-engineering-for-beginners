# Para iniciantes: usando a API do Open-Meteo para praticar engenharia de dados

[🏠 Índice](README.md) · [🇺🇸 English](../en/01-open-meteo-client.md) · [💻 Código](../../code/01-open-meteo-client/)

---

## O que você vai aprender

- [ ] Quais bibliotecas precisamos e por quê
- [ ] Como criar uma sessão que tenta de novo sozinha quando a API falha
- [ ] Como fazer uma requisição segura (timeout, log, checagem de erros)
- [ ] Como salvar a resposta bruta num arquivo
- [ ] Como pedir a chuva diária ao Open-Meteo
- [ ] Como rodar tudo junto

## Antes de começar

Você precisa do **Python 3.10 ou mais novo** (usamos a sintaxe `dict | None`, que só existe a partir do 3.10) e da biblioteca `requests`:

```bash
pip install requests
```

A API histórica do Open-Meteo é gratuita para uso não comercial e **não precisa de chave**. Isso faz dela uma ótima primeira API: você foca em escrever bom código, em vez de brigar com autenticação.

---

## Parte 1 — Bibliotecas

```python
import requests
import os
import time
import logging
import json

from pathlib import Path
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from datetime import datetime, timezone, date
```

- **`requests`** envia requisições HTTP para a API. É a biblioteca mais usada para isso em Python.
- **`os`** lê variáveis de ambiente. Usamos para ler um token secreto, se existir, sem escrevê-lo no código.
- **`time`** mede quanto tempo cada requisição leva.
- **`logging`** escreve mensagens sobre o que o programa está fazendo (uma versão melhor e mais profissional do `print`).
- **`json`** converte dicionários Python em texto JSON, para salvarmos em arquivo.
- **`Path`** (de `pathlib`) representa caminhos de arquivos e pastas. Funciona do mesmo jeito no Windows e no Linux.
- **`Retry`** (de `urllib3`) define as regras para tentar a requisição de novo quando ela falha.
- **`HTTPAdapter`** (de `requests.adapters`) liga essas regras de retentativa à nossa sessão.
- **`datetime`, `timezone`, `date`** lidam com datas e horários: quando o dado foi coletado e quais dias queremos.

> 💡 O `urllib3` é instalado automaticamente com o `requests`, porque o `requests` o usa por dentro. Não precisa instalar separado.

---

## Parte 2 — Configurações

```python
TIMEOUT_S = 30
```

O número máximo de segundos que esperamos a API responder. O nome está em MAIÚSCULAS porque é uma **constante**: um valor definido uma vez e que não muda enquanto o programa roda. O `_S` no final lembra que a unidade é segundos.

> ⚠️ Por padrão, o `requests` espera **para sempre**. Se a API parar de responder, seu programa trava. Use sempre um timeout.

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("api.client")
```

- `basicConfig` configura o log uma vez para o programa inteiro.
- `level=logging.INFO` quer dizer "mostre mensagens de nível INFO ou acima". Sem isso, o nível padrão é WARNING, e as nossas mensagens `log.info(...)` não apareceriam.
- `format` define como cada linha fica: data e hora, nome do logger, nível e mensagem.
- `getLogger("api.client")` cria um logger com nome, para sabermos qual parte do programa escreveu cada mensagem.

> ⚠️ O `basicConfig` só aceita **argumentos nomeados** (`format=...`, `level=...`). Escrever `logging.basicConfig("%(asctime)s ...")` sem o `format=` causa um `TypeError`.

Uma linha de log vai ficar assim:

```
2026-09-24 10:15:02,123 - api.client - INFO - GET https://archive-api... status=200 duration=0.41s
```

---

## Parte 3 — Criando a sessão

```python
def session_maker() -> requests.Session:
    session = requests.Session()
```

Uma **sessão** é um objeto que guarda configurações (cabeçalhos, regras de retentativa) e reaproveita a mesma conexão em várias requisições. É mais rápido do que chamar `requests.get` diretamente toda vez, e configuramos tudo num lugar só.

`-> requests.Session` é uma **dica de tipo** (*type hint*): avisa a quem lê que a função devolve uma sessão. O Python não verifica isso ao rodar; ela existe para pessoas e para ferramentas como o seu editor.

> 💡 Nomes de variáveis em Python são escritos em minúsculas (`session`, e não `Session`). Nomes com inicial maiúscula são usados para classes, como `requests.Session`. Essa convenção vem da PEP 8, o guia de estilo do Python.

### Regras de retentativa

```python
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
```

- **`total=5`**: tenta de novo até 5 vezes.
- **`backoff_factor=1`**: espera mais tempo depois de cada falha (aproximadamente 1, 2, 4, 8 segundos). Isso se chama **backoff exponencial**. Dá tempo para o servidor se recuperar, em vez de bater nele de novo na mesma hora.
- **`status_forcelist`**: os códigos de status HTTP que merecem nova tentativa. Todos são erros **temporários**:
  - `429` — Too Many Requests: passamos do limite da API.
  - `500`, `502`, `503`, `504` — erros do servidor: o problema está do lado deles.
- **`allowed_methods=["GET"]`**: só repete requisições GET. GET apenas lê dados, então repetir é seguro.

**Não** tentamos de novo erros como `400` (requisição mal feita), `401` (não autorizado) ou `404` (não encontrado). Esses são erros **nossos**, e tentar de novo não resolve.

> 💡 Se a API mandar um cabeçalho `Retry-After` ("espere X segundos"), o `Retry` respeita automaticamente.

### Ligando as regras à sessão

```python
    session.mount("https://", HTTPAdapter(max_retries=retry))
```

O `HTTPAdapter` é a parte do `requests` que realmente envia as requisições. Aqui criamos um com as nossas regras de retentativa e o **montamos** na sessão: toda URL que começa com `https://` vai usá-lo.

### Cabeçalhos

```python
    session.headers.update({
        "User-Agent": "estudo-engenharia-dados/0.1 (youremail@example.com)",
        "Accept": "application/json",
    })
```

Cabeçalhos (*headers*) são informações extras enviadas junto com cada requisição.

- **`User-Agent`** identifica quem está chamando: nome do projeto, versão e um contato. É boa educação com APIs públicas, e algumas exigem. **Coloque o seu próprio e-mail aqui.**
- **`Accept: application/json`** avisa à API que queremos a resposta em JSON.

### Token opcional

```python
    token = os.environ.get("API_TOKEN")
    if token:
        session.headers["chave-api-dados"] = token

    return session
```

`os.environ.get("API_TOKEN")` lê a variável de ambiente `API_TOKEN`. Se ela não existir, devolve `None`, e o `if` é pulado.

O Open-Meteo não precisa de token, então essa parte não faz nada aqui. Ela está na função para você reaproveitá-la com APIs que precisam, como o Portal da Transparência, que espera a chave num cabeçalho chamado `chave-api-dados`. Para outra API, troque o nome do cabeçalho pelo que a documentação dela pedir.

> ⚠️ Nunca escreva um token direto no código. Se ele for parar no GitHub, qualquer pessoa pode usá-lo.

---

## Parte 4 — Fazendo uma requisição segura

```python
def get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
```

A função recebe:

- **`session`**: a sessão criada na Parte 3;
- **`url`**: o endereço da API (um texto);
- **`params`**: os parâmetros da consulta, como dicionário. `dict | None = None` quer dizer que pode ser um dicionário **ou** `None`, e que vale `None` se não passarmos nada; ou seja, é opcional.

Ela devolve um dicionário (`-> dict`).

> 💡 Por que `= None` e não `= {}`? Em Python, o valor padrão é criado **uma única vez**, quando a função é definida. Um padrão mutável como `{}` seria compartilhado entre as chamadas e pode causar bugs estranhos. Usar `None` é o jeito padrão de evitar isso.

### Enviando a requisição e medindo o tempo

```python
    start = time.perf_counter()
    resp = session.get(url, params=params, timeout=TIMEOUT_S)
    duration = round(time.perf_counter() - start, 2)
```

- `time.perf_counter()` é um cronômetro preciso. Lemos antes e depois da requisição.
- `session.get(...)` envia a requisição GET. O `requests` transforma o dicionário `params` na parte da URL depois do `?`, por exemplo `?latitude=-16.72&longitude=-43.86`.
- `duration` é a diferença entre as duas leituras, arredondada para 2 casas decimais.

### Registrando no log

```python
    log.info("GET %s status=%s duration=%ss", resp.url, resp.status_code, duration)
```

Registramos a URL completa, o código de status e a duração. Dois detalhes:

- Usamos `resp.url` em vez de `url` porque `resp.url` inclui os parâmetros. Assim fica registrado exatamente o que foi pedido.
- Os `%s` são preenchidos pelo próprio `logging`. É o estilo recomendado para logs, em vez de f-strings.

> ⚠️ Não registre os cabeçalhos: é lá que fica o token. E se uma API colocar a chave **na URL**, também não registre a URL.

### Checando erros

```python
    resp.raise_for_status()
```

Se o código de status for de erro (4xx ou 5xx) e continuar assim depois de todas as retentativas, essa linha lança uma exceção e para o programa. Falhar de forma visível é melhor do que seguir em silêncio com dado ruim.

```python
    if "json" not in resp.headers.get("Content-Type", ""):
        raise ValueError(f"Response is not JSON: {resp.headers.get('Content-Type')}")
```

Algumas APIs devolvem uma página de erro em HTML com status `200` (sucesso!). Aqui checamos o cabeçalho `Content-Type`: se ele não mencionar JSON, paramos. O `""` em `.get("Content-Type", "")` é um valor padrão, usado se o cabeçalho não existir.

> 💡 No `requests`, nomes de cabeçalho não diferenciam maiúsculas de minúsculas: `"Content-Type"` e `"Content-type"` encontram o mesmo cabeçalho.

### Devolvendo dados e metadados

```python
    return {
        "meta": {
            "url": resp.url,
            "status": resp.status_code,
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duration_s": duration,
        },
        "body": resp.json(),
    }
```

Devolvemos duas coisas:

- **`meta`**: informações **sobre** a requisição: qual URL, qual status, **quando** foi coletada e quanto tempo levou. `datetime.now(timezone.utc)` usa UTC, então o horário não depende de onde o código roda.
- **`body`**: a resposta da API, convertida de texto JSON em dicionário Python pelo `resp.json()`.

Guardar os metadados permite responder depois: "quando eu baixei isso, e de onde?"

---

## Parte 5 — Salvando a resposta bruta

```python
def raw_save(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    log.info("raw saved to %s", path)
```

Em engenharia de dados, a **camada raw** guarda o dado exatamente como veio da fonte. Se uma etapa posterior tiver um bug, reprocessamos a partir do arquivo raw sem chamar a API de novo.

Linha por linha:

- **`path.parent.mkdir(parents=True, exist_ok=True)`** cria a pasta onde o arquivo vai ficar. `parents=True` cria também as pastas acima que estiverem faltando; `exist_ok=True` não reclama se a pasta já existir.
- **`tmp = path.with_suffix(".tmp")`** cria um nome de arquivo temporário: `data.json` → `data.tmp`.
- **`json.dumps(...)`** converte o dicionário em texto JSON. `ensure_ascii=False` mantém os acentos legíveis (`ç`, `ã`); `indent=2` deixa o texto formatado.
- **`tmp.write_text(..., encoding="utf-8")`** escreve o texto no arquivo temporário.
- **`tmp.replace(path)`** renomeia o arquivo temporário para o nome final. Renomear é uma operação **atômica**: acontece por completo ou não acontece. Se o programa cair no meio da escrita, o arquivo antigo continua intacto, e você nunca fica com um arquivo pela metade.
- O `-> None` indica que a função não devolve nada; ela só executa uma ação.

> ⚠️ Erro comum: chamar `.parent` ou `.with_suffix` em `content` em vez de `path`. `content` é um dicionário, e dicionários não têm esses métodos, então dá `AttributeError`. A pasta e o nome do arquivo sempre vêm de `path`.

---

## Parte 6 — Pedindo os dados de chuva ao Open-Meteo

```python
def open_meteo_rain(session: requests.Session, lat: float, lon: float, start: date, end: date) -> dict:
    return get_json(
        session,
        "https://archive-api.open-meteo.com/v1/archive",
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "precipitation_sum",
            "timezone": "America/Sao_Paulo",
        },
    )
```

Essa função sabe **o que** pedir ao Open-Meteo. O **como** (retentativas, timeout, checagens) fica no `get_json`. Separar essas duas responsabilidades permite escrever uma função nova para outra API e reaproveitar o `get_json` sem mudar nada.

Os parâmetros enviados à API:

| Parâmetro | Significado |
|---|---|
| `latitude`, `longitude` | O local. Valores negativos são sul e oeste. |
| `start_date`, `end_date` | O período, no formato `AAAA-MM-DD`. O `.isoformat()` transforma um `date` nesse texto. |
| `daily` | Qual variável diária queremos. `precipitation_sum` é o total de chuva do dia, em mm. |
| `timezone` | Qual fuso horário define onde "um dia" começa e termina. |

A função recebe as datas como **parâmetros**, em vez de usar datas fixas. É isso que a torna reaproveitável: a mesma função baixa um dia, uma semana ou dez anos (isso se chama **backfill**).

---

## Parte 7 — Rodando tudo

```python
if __name__ == "__main__":
    session = session_maker()

    start, end = date(2024, 3, 1), date(2024, 3, 7)
    weather = open_meteo_rain(session, -16.72, -43.86, start, end)
    raw_save(weather, Path(f"data/raw/open_meteo/{start}_{end}.json"))

    daily = weather["body"]["daily"]
    for day, rain in zip(daily["time"], daily["precipitation_sum"]):
        print(f"{day}: {rain} mm")
```

- **`if __name__ == "__main__":`** — esse bloco só roda quando você executa o arquivo diretamente (`python client.py`). Se outro arquivo importar essas funções, o bloco é pulado.
- **`session_maker()`** cria a sessão uma vez.
- **`start, end = ...`** define o período: a primeira semana de março de 2024.
- **`open_meteo_rain(...)`** pede a chuva de Montes Claros, MG (latitude -16,72, longitude -43,86).
- **`raw_save(...)`** salva a resposta em `data/raw/open_meteo/2024-03-01_2024-03-07.json`. Colocar as datas no nome do arquivo facilita encontrar cada período.
- **`weather["body"]["daily"]`** abre a parte da resposta com os dados diários. Ela tem duas listas do mesmo tamanho: `time` (os dias) e `precipitation_sum` (a chuva).
- **`zip(...)`** percorre as duas listas juntas, pareando cada dia com a sua chuva.

Rode a partir da raiz do repositório:

```bash
cd code/01-open-meteo-client
python client.py
```

Você deve ver as linhas de log seguidas de uma linha por dia, no formato `2024-03-01: X.X mm`, e um novo arquivo JSON em `data/raw/open_meteo/`.

---

## Código completo

> O mesmo código está em [`code/01-open-meteo-client/client.py`](../../code/01-open-meteo-client/client.py).

```python
import requests
import os
import time
import logging
import json

from pathlib import Path
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from datetime import datetime, timezone, date

TIMEOUT_S = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("api.client")


def session_maker() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))

    session.headers.update({
        "User-Agent": "estudo-engenharia-dados/0.1 (youremail@example.com)",
        "Accept": "application/json",
    })

    token = os.environ.get("API_TOKEN")
    if token:
        session.headers["chave-api-dados"] = token

    return session


def get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    start = time.perf_counter()
    resp = session.get(url, params=params, timeout=TIMEOUT_S)
    duration = round(time.perf_counter() - start, 2)

    log.info("GET %s status=%s duration=%ss", resp.url, resp.status_code, duration)

    resp.raise_for_status()

    if "json" not in resp.headers.get("Content-Type", ""):
        raise ValueError(f"Response is not JSON: {resp.headers.get('Content-Type')}")

    return {
        "meta": {
            "url": resp.url,
            "status": resp.status_code,
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duration_s": duration,
        },
        "body": resp.json(),
    }


def raw_save(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    log.info("raw saved to %s", path)


def open_meteo_rain(session: requests.Session, lat: float, lon: float, start: date, end: date) -> dict:
    return get_json(
        session,
        "https://archive-api.open-meteo.com/v1/archive",
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "precipitation_sum",
            "timezone": "America/Sao_Paulo",
        },
    )


if __name__ == "__main__":
    session = session_maker()

    start, end = date(2024, 3, 1), date(2024, 3, 7)
    weather = open_meteo_rain(session, -16.72, -43.86, start, end)
    raw_save(weather, Path(f"data/raw/open_meteo/{start}_{end}.json"))

    daily = weather["body"]["daily"]
    for day, rain in zip(daily["time"], daily["precipitation_sum"]):
        print(f"{day}: {rain} mm")
```

---

## Exercícios

1. Troque as coordenadas pelas da sua cidade e baixe um mês inteiro.
2. Acrescente `"temperature_2m_max"` ao parâmetro `daily` (separe as variáveis com vírgula: `"precipitation_sum,temperature_2m_max"`) e imprima os dois valores.
3. Passe uma data em formato errado direto na URL e veja o que o `raise_for_status()` faz.
4. Escreva uma função nova, `bcb_series(session, code, start, end)`, para a API do Banco Central, reaproveitando `session_maker` e `get_json` sem alterá-los.

---

[🏠 Índice](README.md) · [🇺🇸 English](../en/01-open-meteo-client.md) · [💻 Código](../../code/01-open-meteo-client/)
