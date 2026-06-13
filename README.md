# vaultGFS

`vaultGFS` é um utilitário de backup em Python para executar jobs independentes de backup de arquivos e dumps lógicos de MySQL, com organização no estilo GFS: backups mensais completos, semanais diferenciais e diários incrementais.

O projeto foi desenhado para ser genérico e publicável. A configuração real fica fora do repositório. O arquivo versionado `config.toml.model` serve como modelo.

## Principais recursos

- Backup de diretórios por job.
- Estratégia GFS lógica para filesystem:
 - `full`: backup completo.
 - `diff`: diferencial desde o último `full` bem-sucedido.
 - `inc`: incremental desde o último backup conhecido no catálogo.
- Separação de arquivos por classe:
 - `storage.tar` para arquivos já comprimidos ou pouco compressíveis.
 - `compressible.tar.zst` para arquivos com melhor ganho de compressão.
- Dumps MySQL por schema, com compressão `zstd`.
- Catálogo SQLite para registrar execuções e snapshots.
- `manifest.json` por execução.
- Controle global de concorrência para formar uma fila de backups.
- Suporte a `nice`, `ionice` e limite de threads de compressão.
- Agendamento externo por cron.
- Configuração via TOML.

## Estrutura do projeto

```text
vaultGFS/
├── config.toml.model # modelo de configuração, versionado
├── docs/requirements.md # requisitos e decisões de projeto
├── pyproject.toml # metadata Python e entrypoints
├── README.md
└── src/vaultgfs/
 ├── catalog.py # catálogo SQLite
 ├── cli_backup.py # CLI principal de execução
 ├── cli_reload.py # validação/ajustes assistidos de ambiente
 ├── cli_restore.py # placeholder de restauração futura
 ├── config.py # leitura/validação da configuração
 ├── fs_backup.py # backup filesystem/GFS
 └── mysql_dump.py # dump lógico MySQL
```

## Instalação básica

Requisitos mínimos:

- Linux.
- Python 3.11+.
- `tar`.
- `zstd`.
- `sqlite3` para inspeção manual do catálogo.
- `mysql-client`/`mysqldump` se usar jobs MySQL.
- `cron` se usar agendamento.

Instalação local em modo editável:

```bash
python3 -m pip install -e .
```

Isso publica os entrypoints:

```text
vaultgfs-backup
vaultgfs-reload
vaultgfs-restore
```

Em instalação de produção, normalmente são criados wrappers em `/usr/local/bin`, por exemplo com baixa prioridade:

```bash
exec nice -n 15 ionice -c2 -n7 python3 -m vaultgfs.cli_backup "$@"
```

## Arquivo de configuração

O caminho padrão da configuração é:

```text
/opt/vaultGFS/config.toml
```

O arquivo real **não deve ser versionado**, pois pode conter senhas. Use o modelo:

```text
config.toml.model
```

Exemplo de criação:

```bash
cp config.toml.model config.toml
```

Em produção, recomenda-se restringir permissões:

```bash
chown root:vaultgfs /opt/vaultGFS/config.toml
chmod 0640 /opt/vaultGFS/config.toml
```

## Seção `[defaults]`

Exemplo:

```toml
[defaults]
state_dir = "/var/lib/vaultgfs"
catalog = "/var/lib/vaultgfs/catalog.db"
destination_root = "/mnt/usb1/backups"
run_user = "vaultgfs"
run_group = "vaultgfs"
compression_level = 22
compression_threads = 2
max_concurrent_backups = 1
lock_wait_seconds = 10
```

Campos:

- `state_dir`: diretório de estado do vaultGFS. Também abriga arquivos de lock.
- `catalog`: caminho do catálogo SQLite.
- `destination_root`: raiz geral dos backups. Jobs podem usar destinos específicos.
- `run_user`: usuário recomendado para executar backups.
- `run_group`: grupo recomendado.
- `compression_level`: nível padrão do `zstd`.
- `compression_threads`: número padrão de threads de compressão.
- `max_concurrent_backups`: quantidade máxima de backups simultâneos.
- `lock_wait_seconds`: intervalo entre tentativas de obter slot de execução.

### Fila e concorrência

`max_concurrent_backups = 1` faz o sistema trabalhar como fila serial.

Se vários jobs forem disparados ao mesmo tempo:

1. O primeiro pega o slot.
2. Os demais ficam aguardando.
3. A cada `lock_wait_seconds`, eles registram uma mensagem `WAIT concurrency` e tentam novamente.
4. Quando o slot é liberado, o próximo job segue.

`lock_wait_seconds` **não é timeout**. O processo não desiste por causa desse valor. Ele espera até conseguir executar.

## Classificação de arquivos

A lista `storage_extensions` define extensões consideradas pouco compressíveis ou já comprimidas:

```toml
storage_extensions = [
 ".jpg", ".jpeg", ".png", ".mp4", ".zip", ".rar", ".7z", ".pdf"
]
```

Arquivos com essas extensões entram em:

```text
<backup-id>.storage.tar
```

Os demais entram em:

```text
<backup-id>.compressible.tar.zst
```

Isso evita gastar CPU tentando recomprimir arquivos que tendem a não ganhar muito com compressão.

## Configuração MySQL

Exemplo:

```toml
[mysql]
host = "localhost"
port = 3306
user = "vaultGFS"
password = "CHANGE_ME"
socket = "/var/run/mysqld/mysqld.sock"
ssl_mode = "DISABLED"
```

Campos:

- `host`: host MySQL, usado quando `socket` não for informado.
- `port`: porta MySQL.
- `user`: usuário usado por `mysqldump`.
- `password`: senha. Não versionar configuração real.
- `socket`: socket local. Quando definido, tem preferência sobre host/porta.
- `ssl_mode`: modo SSL repassado ao cliente MySQL quando aplicável.

Permissões mínimas recomendadas para o usuário MySQL de backup:

```sql
GRANT SELECT, SHOW VIEW, EVENT, TRIGGER ON schema.* TO 'vaultGFS'@'localhost';
GRANT SHOW_ROUTINE ON *.* TO 'vaultGFS'@'localhost';
```

Schemas de sistema não são aceitos como alvo de backup:

```text
mysql
information_schema
performance_schema
sys
```

## Jobs de filesystem

Exemplo:

```toml
[[jobs]]
name = "example-filesystem"
enabled = true
type = "filesystem-gfs"
source = "/path/to/source"
destination = "/mnt/usb1/backups/example-filesystem"
skip_if_unchanged = true
compression_level = 22
compression_threads = 2
schedule_full = "10 0 1 * *"
schedule_diff = "10 0 * * 0"
schedule_inc = "10 0 * * 1-6"
```

Campos:

- `name`: identificador único do job.
- `enabled`: se `false`, o job é ignorado.
- `type`: para arquivos, usar `filesystem-gfs`.
- `source`: diretório de origem.
- `destination`: diretório base do backup desse job.
- `skip_if_unchanged`: se `true`, não grava novo backup quando nada mudou.
- `compression_level`: sobrescreve o padrão global.
- `compression_threads`: sobrescreve o padrão global.
- `schedule_full`: expressão cron sugerida para backup completo.
- `schedule_diff`: expressão cron sugerida para diferencial.
- `schedule_inc`: expressão cron sugerida para incremental.

Saída típica:

```text
/mnt/usb1/backups/example-filesystem/full/example-filesystem-full-YYYYMMDD-HHMMSS/
├── example-filesystem-full-YYYYMMDD-HHMMSS.storage.tar
├── example-filesystem-full-YYYYMMDD-HHMMSS.compressible.tar.zst
└── manifest.json
```

Nem todos os jobs geram os dois arquivos. Se todos os arquivos forem classificados como `storage`, só haverá `.storage.tar`. Se todos forem compressíveis, só haverá `.compressible.tar.zst`.

## Jobs MySQL

Exemplo:

```toml
[[jobs]]
name = "example-mysql-schema"
enabled = true
type = "mysql-dump"
schemas = ["example_schema"]
destination = "/mnt/usb1/backups/mysql/example_schema"
skip_if_unchanged = false
compression_level = 22
compression_threads = 1
resource_monitor = "passive"
nice = 15
ionice_class = 2
ionice_level = 7
schedule = "10 0 * * *"
```

Campos:

- `type`: para MySQL, usar `mysql-dump`.
- `schemas`: lista de schemas a exportar.
- `destination`: diretório de saída.
- `compression_level`: nível `zstd`.
- `compression_threads`: threads do `zstd`.
- `resource_monitor`: `off`, `passive` ou `active`.
- `nice`: prioridade de CPU dos subprocessos.
- `ionice_class`: classe de I/O.
- `ionice_level`: nível de I/O.
- `schedule`: expressão cron sugerida.

Saída típica:

```text
/mnt/usb1/backups/mysql/example_schema/example_schema-YYYYMMDD-HHMMSS.sql.zst
```

## Monitoramento de recursos em MySQL

Modos:

- `off`: não registra métricas adicionais.
- `passive`: registra métricas, mas não interfere.
- `active`: pode pausar, retomar ou abortar subprocessos se limites forem excedidos.

Métricas registradas:

- CPU dos subprocessos.
- Memória dos subprocessos.
- Load average de 1 minuto.
- Uso de swap.
- Tamanho do arquivo de saída.
- Crescimento do arquivo de saída.

Exemplo de log:

```text
START mysql dump job=mysql-jarvis schema=jarvis compression_level=22 compression_threads=1 monitor=passive
MONITOR job=mysql-jarvis pids=123,124 cpu_percent=1.2 mem_percent=0.0 load1=0.14 swap_percent=96.4 output_bytes=14744 delta_bytes=0
SUCCESS mysql-jarvis: dumped 1 schema(s) -> /mnt/usb1/backups/mysql/jarvis
```

Observação: limitar `zstd` não limita todo o impacto do dump. `mysqldump` e o próprio `mysqld` ainda podem gerar I/O, uso de cache e concorrência no banco.

## Executável `vaultgfs-backup`

Executa um job.

Uso:

```bash
vaultgfs-backup --job JOB [--level full|diff|inc] [--config /path/config.toml]
```

Para jobs `filesystem-gfs`, `--level` é obrigatório:

```bash
vaultgfs-backup --job example-filesystem --level full
vaultgfs-backup --job example-filesystem --level diff
vaultgfs-backup --job example-filesystem --level inc
```

Para jobs `mysql-dump`, não se usa `--level`:

```bash
vaultgfs-backup --job example-mysql-schema
```

Todo job registra início e fim:

```text
RUN_START job=example-filesystem level=full slot=0 started=2026-06-13T00:10:00
SUCCESS example-filesystem full: 123 files -> /backup/path
RUN_END job=example-filesystem level=full slot=0 ended=2026-06-13T00:15:00 duration_seconds=300.123
```

## Executável `vaultgfs-reload`

Valida a configuração e propõe correções de ambiente.

Uso:

```bash
vaultgfs-reload --config /opt/vaultGFS/config.toml
vaultgfs-reload --config /opt/vaultGFS/config.toml --yes
```

Responsabilidades atuais:

- Validar estrutura da configuração.
- Verificar usuário de execução.
- Verificar diretórios de estado e destino.
- Verificar existência de origens filesystem.
- Testar acesso MySQL por schema.
- Propor ajustes interativos.

Nota: a sincronização automática de agendamentos ainda está em evolução. O modelo operacional recomendado atualmente é cron-line explícito, mantendo os jobs serializados pelo lock global do próprio `vaultgfs-backup`.

## Executável `vaultgfs-restore`

Ainda é um placeholder:

```bash
vaultgfs-restore
```

Saída atual:

```text
vaultgfs-restore is planned for a future version.
```

Restauração interativa, retenção, rotação e cópia externa são itens planejados para versões futuras.

## Agendamento com cron

O projeto não requer daemon permanente. A forma recomendada de agendar é cron.

Exemplo com todos os jobs disparando às 00:10 e execução serializada por `max_concurrent_backups = 1`:

```cron
# FULL mensal: dia 1
10 0 1 * * /usr/local/bin/vaultgfs-backup --job example-filesystem --level full >> /var/log/vaultgfs/cron-example-full.log 2>&1

# DIFF semanal: domingo, exceto dia 1
10 0 * * 0 [ "$(date +\%d)" != "01" ] && /usr/local/bin/vaultgfs-backup --job example-filesystem --level diff >> /var/log/vaultgfs/cron-example-diff.log 2>&1

# INC diário: segunda a sábado, exceto dia 1
10 0 * * 1-6 [ "$(date +\%d)" != "01" ] && /usr/local/bin/vaultgfs-backup --job example-filesystem --level inc >> /var/log/vaultgfs/cron-example-inc.log 2>&1

# MySQL diário
10 0 * * * /usr/local/bin/vaultgfs-backup --job example-mysql-schema >> /var/log/vaultgfs/cron-example-mysql.log 2>&1
```

Se todos os jobs forem agendados no mesmo minuto, o lock global evita execução concorrente acima do limite configurado.

## Logs

Recomenda-se gravar logs em:

```text
/var/log/vaultgfs
```

Exemplos:

```text
/var/log/vaultgfs/cron-fileserver-docsafe-full.log
/var/log/vaultgfs/cron-fileserver-docsafe-diff.log
/var/log/vaultgfs/cron-fileserver-docsafe-inc.log
/var/log/vaultgfs/cron-mysql-biserp.log
```

Para cada execução, verifique:

- `RUN_START`.
- `SUCCESS`, `SKIPPED` ou erro.
- `RUN_END`.
- `duration_seconds`.
- Mensagens `WAIT concurrency`, se houve fila.
- Linhas `MONITOR`, em jobs MySQL com monitoramento.

## Catálogo SQLite

O catálogo padrão fica em:

```text
/var/lib/vaultgfs/catalog.db
```

Ele registra:

- Execuções de backup.
- Status.
- Destino.
- Manifest.
- Snapshot de arquivos para cálculo de diferenciais/incrementais.

O catálogo é parte do estado operacional. Não deve ser versionado.

## Validação manual de artefatos

Validar `.tar`:

```bash
tar -tf backup.storage.tar
```

Validar `.tar.zst`:

```bash
zstd -t backup.compressible.tar.zst
tar --use-compress-program='zstd -d' -tf backup.compressible.tar.zst
```

Validar dump MySQL comprimido:

```bash
zstd -t schema-YYYYMMDD-HHMMSS.sql.zst
```

## Segurança

- Não versionar `config.toml` real.
- Não versionar senhas, tokens, dumps, catálogos ou logs.
- Usar usuário dedicado para execução.
- Restringir leitura do arquivo de configuração.
- Conceder ao usuário MySQL apenas permissões necessárias para dump.
- Preferir execução com baixa prioridade (`nice`/`ionice`) em servidores de produção.

## Estado atual do projeto

Funcional hoje:

- Backup filesystem `full`, `diff`, `inc`.
- Dump MySQL por schema.
- Compressão `zstd`.
- Catálogo SQLite.
- Manifests.
- Fila por lock global.
- Logs com início, fim e duração.
- Monitoramento de recursos para MySQL.

Planejado:

- Monitoramento de recursos também para filesystem.
- `vaultgfs-restore` interativo.
- Política de retenção/rotação.
- Cópia externa/off-site.
- Sincronização de cron pelo `vaultgfs-reload`.
