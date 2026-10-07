# Data Engineering for Beginners · Engenharia de Dados para Iniciantes

A bilingual, hands-on handbook that explains data engineering code **line by line**, written while I practice.
Uma apostila bilíngue e prática que explica código de engenharia de dados **linha por linha**, escrita enquanto eu pratico.

| | |
|---|---|
| 🇺🇸 **English** | [Start here → docs/en](docs/en/README.md) |
| 🇧🇷 **Português** | [Comece aqui → docs/pt](docs/pt/README.md) |

## Lessons · Lições

| # | Lesson | Lição | Code · Código |
|---|---|---|---|
| 01 | [Making safe API requests (Open-Meteo)](docs/en/01-open-meteo-client.md) | [Fazendo requisições seguras a uma API (Open-Meteo)](docs/pt/01-open-meteo-client.md) | [`code/01-open-meteo-client`](code/01-open-meteo-client/) |
| 02 | [From raw data to a clean table](docs/en/02-raw-to-staging.md) | [Do dado bruto para uma tabela limpa](docs/pt/02-raw-to-staging.md) | [`code/02-raw-to-staging`](code/02-raw-to-staging/) |

Lessons build on each other: run them in order, because each one reads the data saved by the previous lesson.
As lições se complementam: rode-as em ordem, porque cada uma lê os dados salvos pela lição anterior.

## Repository structure · Estrutura do repositório

```
docs/
├── en/                     # lessons in English
└── pt/                     # lições em português
code/
├── 01-open-meteo-client/   # runnable code for each lesson · código executável de cada lição
└── 02-raw-to-staging/
data/                       # created by the lessons (ignored by git) · criada pelas lições (ignorada pelo git)
├── raw/                    # data exactly as the API sent it · dado exatamente como a API enviou
└── staging/                # clean, typed, validated data · dado limpo, tipado e validado
```

Each lesson has the **same file name** in both languages, and each code folder has the **same number** as its lesson.
Cada lição tem o **mesmo nome de arquivo** nos dois idiomas, e cada pasta de código tem o **mesmo número** da lição.

## Setup

Python 3.10+

```bash
pip install -r requirements.txt
```

## Author · Autor

Matheus Seiti Vicente Matsuoka · [GitHub](https://github.com/M-Seiti)