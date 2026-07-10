# Monitor de Impressoras

> Plataforma web para monitoramento, auditoria e análise do parque de impressão.

![Versão](https://img.shields.io/badge/versão-1.1.0-38bdf8)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3-000000?logo=flask&logoColor=white)
![MariaDB](https://img.shields.io/badge/MariaDB-persistência-003545?logo=mariadb&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-pronto-2496ED?logo=docker&logoColor=white)

## Sobre o sistema

O **Monitor de Impressoras** centraliza informações operacionais e gerenciais de impressoras em rede. O sistema coleta dados dos equipamentos via SNMP, mantém históricos no MariaDB e relaciona eventos do servidor de impressão aos usuários responsáveis.

Com uma única interface, é possível acompanhar a disponibilidade dos equipamentos, volume de páginas, custos estimados, níveis de toner e utilização por usuário.

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
- **Monitoramento:** SNMP com coleta periódica em threads.
- **Persistência:** MariaDB.
- **Frontend:** HTML, CSS e JavaScript sem frameworks.
- **Implantação:** Docker e Docker Compose.

## Execução

Configure as variáveis de ambiente do MariaDB, da API e do monitoramento em um arquivo `.env`. Depois, execute:

```bash
docker compose up -d --build
```

A aplicação ficará disponível, por padrão, em:

```text
http://localhost:8080
```

> Não versione arquivos `.env`, senhas, credenciais do banco ou communities SNMP reais.

## Versionamento

O projeto utiliza [Versionamento Semântico](https://semver.org/lang/pt-BR/) no formato `MAJOR.MINOR.PATCH`.

A versão deve permanecer sincronizada no arquivo `VERSION`, na interface e na tag Git do lançamento.

Versão atual: **v1.1.0**

## Próximas evoluções

- Comparação mensal entre contadores SNMP e eventos do servidor de impressão.
- Indicadores executivos e comparação com o mês anterior.
- Alertas automáticos de divergência de contadores.
- Relatórios de custos por usuário e setor.

## Segurança

A API oferece autenticação HTTP Basic opcional. Em produção, recomenda-se habilitar as credenciais, utilizar HTTPS e restringir o acesso de rede ao MariaDB e às impressoras.

## Licença e autoria

Defina os dados de autoria e a licença de distribuição antes de publicar o projeto externamente.

