# Central de Monitoramento

> Plataforma web única para monitorar serviços de rede e o parque de impressão.

![Versão](https://img.shields.io/badge/versão-2.2.0-38bdf8)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3-000000?logo=flask&logoColor=white)
![MariaDB](https://img.shields.io/badge/MariaDB-persistência-003545?logo=mariadb&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-pronto-2496ED?logo=docker&logoColor=white)

## Sobre o sistema

Esta aplicação reúne o MonitorNet e o monitor de impressoras em um único servidor Flask, menu e endereço. O módulo de rede acompanha serviços HTTP e hosts por ping, registra incidentes e pode enviar alertas por e-mail. O módulo de impressão coleta dados via SNMP e relaciona eventos do servidor de impressão aos usuários responsáveis.

Os monitores têm ciclos de coleta independentes e tabelas separadas no MariaDB. O MonitorNet usa tabelas com prefixo `monitor_`; os cadastros e históricos de impressoras continuam nas tabelas existentes.

## O que o sistema resolve

- Centraliza o acompanhamento de todas as impressoras cadastradas.
- Identifica rapidamente equipamentos online e offline.
- Mostra alertas de toner para apoiar a manutenção preventiva.
- Registra o volume diário e mensal de impressões.
- Mantém histórico consolidado para auditoria.
- Identifica quais usuários imprimiram em cada equipamento.
- Estima custos com base no tipo de token configurado.
- Facilita a análise por meio de gráficos e relatórios.

## Principais recursos

### Dashboard operacional

Visão rápida do parque de impressão, com totais de equipamentos online e offline, dados técnicos, contadores e alertas de toner.

### Monitoramento via SNMP

Coleta automática de informações como nome, modelo, série, patrimônio, localização, endereço MAC, uptime, contadores, toner e status.

### Gráficos e indicadores

Comparação de impressões diárias e mensais por equipamento, evolução histórica e ranking de usuários por quantidade de páginas.

### Auditoria de impressão

Consulta dos trabalhos enviados pelo servidor de impressão, incluindo usuário, data e hora, computador, documento, páginas e impressora utilizada.

### Cruzamento entre usuário e impressora

Os eventos são associados ao equipamento pelo padrão de porta `PAPERCUT_<IP>`. Ao clicar em uma impressora no gráfico, o sistema apresenta os usuários, trabalhos e páginas do período selecionado.

### Gestão de equipamentos

Cadastro e exclusão de impressoras diretamente pela interface, com validação de IP, community SNMP, identificador e tipo de token.

### Relatório mensal

Geração de um resumo mensal por impressora, com volume produzido, classificação do token e custo estimado.

## Telas disponíveis

| Tela | Finalidade |
|---|---|
| **Rede** (`/rede`) | Disponibilidade, latência, incidentes e alertas dos serviços |
| **Dashboard** | Acompanhamento operacional e alertas |
| **Gráficos** | Indicadores diários, mensais e por usuário |
| **Auditoria** | Histórico consolidado das leituras |
| **Configurações** | Cadastro e gerenciamento das impressoras |

## Como os dados se relacionam

```text
Impressoras em rede
        │
        │ SNMP
        ▼
Monitor de Impressoras ─────► MariaDB
        ▲                       │
        │                       │ histórico e auditoria
        │ eventos               ▼
Servidor de impressão     Gráficos e relatórios
```

O contador físico é obtido por SNMP. Os eventos por usuário chegam do servidor de impressão e são relacionados ao IP cadastrado por meio da porta `PAPERCUT_<IP>`.

## Arquitetura

- **Backend:** Python 3.11 e Flask.
- **Monitoramento:** SNMP para impressoras; ping e HTTP para serviços de rede, com coleta periódica em threads.
- **Switches:** SNMPv2c de leitura para informações do equipamento e interfaces, com atualização periódica independente do ping.
- **Persistência:** MariaDB.
- **Frontend:** HTML, CSS e JavaScript sem frameworks.
- **Implantação:** Docker e Docker Compose.

## Execução

Copie `.env.example` para `.env` e configure as credenciais do MariaDB. Para preservar os registros atuais do MonitorNet em outro banco, configure também `NETWORK_MARIADB_*` com os dados daquele banco. Se essas variáveis ficarem vazias, o monitor de rede usará o mesmo banco do monitor de impressoras e criará nele as tabelas `monitor_*`.

Se os bancos antigos estiverem em servidores diferentes, o contêiner precisa alcançar ambos pela rede. Use nomes ou IPs acessíveis a partir do contêiner; `localhost` dentro dele aponta para o próprio contêiner. Não copie o arquivo SQLite legado: o MonitorNet já usa MariaDB em execução.

Depois, execute:

```bash
docker compose up -d --build
```

A aplicação ficará disponível, por padrão, em:

```text
http://localhost:8080/       # impressoras
http://localhost:8080/rede   # serviços de rede
```

A API de impressoras mantém `/api/*`; a API do MonitorNet está em `/api/rede/*`. A porta antiga `3050` deixa de ser necessária quando os clientes usarem os novos endereços. Com `API_USER` e `API_PASSWORD` configurados, as páginas e as duas APIs exigem autenticação HTTP Basic. O monitor de rede precisa de `iputils-ping`, instalado pela imagem Docker.

Se a configuração ou a conexão do banco de rede falhar, `/api/rede/*` responde `503`; a parte de impressoras continua disponível. Configure `SMTP_*` para ativar os alertas de rede por e-mail.

### Cadastrar um switch

Em `/rede`, clique em **Adicionar serviço**, escolha **Switch (ping + SNMPv2c)** e informe o IP de gerenciamento, a community de leitura e a porta UDP (normalmente `161`). O switch deve aceitar consultas SNMPv2c originadas do contêiner. O ping continua responsável por disponibilidade, latência, perda e alertas de queda; a coleta SNMP roda a cada `NETWORK_SNMP_INTERVAL_SECONDS` (padrão: 60 segundos). Ao abrir o cartão do switch, aparecem nome, descrição, localização, uptime e até 128 interfaces com estado administrativo/operacional, octetos e erros. Os contadores de octetos preferem 64 bits e usam 32 bits quando necessário, conforme a [IF-MIB](https://www.rfc-editor.org/rfc/rfc2863).

A community fica no MariaDB na tabela `monitor_switch_config` e não é enviada nas respostas da API. Use uma community com acesso somente de leitura e proteja o acesso ao banco e à rede de gerenciamento. Esta implementação não inclui SNMPv3 nem métricas específicas de fabricantes, como CPU ou temperatura. Se o ping for bloqueado, o painel de disponibilidade pode marcar o switch como offline mesmo quando a leitura SNMP funcionar.

> Não versione arquivos `.env`, senhas, credenciais do banco ou communities SNMP reais.

## Versionamento

O projeto utiliza [Versionamento Semântico](https://semver.org/lang/pt-BR/) no formato `MAJOR.MINOR.PATCH`.

A versão deve permanecer sincronizada no arquivo `VERSION`, na interface e na tag Git do lançamento.

Versão atual: **v2.2.0**

## Próximas evoluções

- Comparação mensal entre contadores SNMP e eventos do servidor de impressão.
- Indicadores executivos e comparação com o mês anterior.
- Alertas automáticos de divergência de contadores.
- Relatórios de custos por usuário e setor.

## Segurança

A API oferece autenticação HTTP Basic opcional. Em produção, recomenda-se habilitar as credenciais, utilizar HTTPS e restringir o acesso de rede ao MariaDB e às impressoras.

## Licença e autoria

Defina os dados de autoria e a licença de distribuição antes de publicar o projeto externamente.

