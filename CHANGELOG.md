# Histórico de versões

## [2.2.0] - 2026-10-02

### Adicionado

- Cadastro de switches com community e porta SNMPv2c.
- Coleta periódica de informações do equipamento e interfaces pela MIB padrão.
- Exibição dos dados SNMP na tela de detalhes, sem expor a community pela API.

## [2.1.0] - 2026-10-02

### Adicionado

- MonitorNet integrado ao servidor Flask, em `/rede` e `/api/rede/*`.
- Navegação compartilhada entre rede e impressoras.
- Configuração de banco de rede independente e suporte a ping na imagem Docker.

### Corrigido

- Registro da autenticação HTTP Basic opcional nas páginas e APIs.

## [1.1.0] - 2026-07-10

### Adicionado

- Exibição da versão do sistema nas páginas de dashboard, gráficos e configurações.
- Inclusão do arquivo de versão na imagem Docker.

### Corrigido

- Serialização do horário retornado pelo MariaDB no endpoint de histórico.
- Exibição dos registros na tabela de auditoria.
