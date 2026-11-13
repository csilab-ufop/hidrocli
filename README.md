# HidroCLI

An python application tool to request and sync data from ANA Hidro WebServices.

## Setup

- Requires [sqlite3](https://sqlite.org/index.html).
- Setup your python enviroment and install dependencies:
``` shell
    pip install .
```

## Usage

```
usage: hidrocli [-h] [--hidro HIDRO] [--client CLIENT]
                [--max-workers MAX_WORKERS] [--batch-size BATCH_SIZE]
                [--log-level {TRACE,VERBOSE,DEBUG,INFO,WARNING,ERROR}]
                [--skip-series-jobs]
                [--skip-for [{Chuvas,ResumoDescarga,CurvaDescarga,Sedimentos,QualAgua,Cotas,Granulometria,PerfilTransversal,Vazoes} ...]]
                [--run-for [{Chuvas,ResumoDescarga,CurvaDescarga,Sedimentos,QualAgua,Cotas,Granulometria,PerfilTransversal,Vazoes} ...]]
                [--stations [STATIONS ...]] [--save-json]
                [--json-dir JSON_DIR]

options:
  -h, --help            show this help message and exit
  --hidro HIDRO         Path to Hidro Database file
  --client CLIENT       Path to Client Database file
  --max-workers MAX_WORKERS
                        Maximum number of worker threads
  --batch-size BATCH_SIZE
                        Batch size threshold to write job data on Hidro
                        Database
  --log-level {TRACE,VERBOSE,DEBUG,INFO,WARNING,ERROR}
                        Set logging level
  --skip-series-jobs    Skip all series jobs when present
  --skip-for [{Chuvas,ResumoDescarga,CurvaDescarga,Sedimentos,QualAgua,Cotas,Granulometria,PerfilTransversal,Vazoes} ...]
                        Skip job creation and requesition for the given
                        choices
  --run-for [{Chuvas,ResumoDescarga,CurvaDescarga,Sedimentos,QualAgua,Cotas,Granulometria,PerfilTransversal,Vazoes} ...]
                        Runs only the choosen Jobs
  --stations [STATIONS ...]
                        Stations codes to request data
  --save-json           Save raw JSON payloads retrieved from the API
  --json-dir JSON_DIR   Directory where raw JSON payloads are saved

```

## Saving payloads

Saving is disabled by default. Pass `--save-json` to keep the raw payloads
returned by the API; `--json-dir` selects the output directory (default
`json`). Files mirror the repository cache layout:

- base jobs: `DIR/<Job>.json`
- `Estacao`: `DIR/Estacao/Estacao_<UF>.json`
- series jobs: `DIR/<Job>/station_<code>_<start>_<end>.json`

Files are written only; nothing is read back from them.

## Documentation

- [ETL](https://github.com/ctxmc/hidrocli/wiki/etl)
- [Hidro Database](https://github.com/ctxmc/hidrocli/wiki/hidro-database)
- [Client Database](https://github.com/ctxmc/hidrocli/wiki/client-database)
- [Hidro Models](https://github.com/ctxmc/hidrocli/wiki/hidro-models)
- [Client Models](https://github.com/ctxmc/hidrocli/wiki/client-models)
- [Config](https://github.com/ctxmc/hidrocli/wiki/config)
- [Use Cases](https://github.com/ctxmc/hidrocli/wiki/Use-Cases)
