# 🖨️ Como Adicionar Novas Impressoras

## Método Simples (Recomendado)

O código agora é **totalmente escalável**. Para adicionar uma nova impressora:

### 1️⃣ Abra o arquivo `app.py`

### 2️⃣ Localize a seção `IMPRESSORAS_CONFIG` (linhas 7-22)

Você verá algo assim:

```python
IMPRESSORAS_CONFIG = [
    {
        'id': 'impressora1',
        'ip': '192.168.0.39',
        'community': 'oabce'
    },
    {
        'id': 'impressora2',
        'ip': '192.168.0.32',
        'community': 'oabce'
    },
]
```

### 3️⃣ Adicione uma nova impressora

Simplesmente **copie e cole** um bloco e altere os valores:

```python
IMPRESSORAS_CONFIG = [
    {
        'id': 'impressora1',
        'ip': '192.168.0.39',
        'community': 'oabce'
    },
    {
        'id': 'impressora2',
        'ip': '192.168.0.32',
        'community': 'oabce'
    },
    {
        'id': 'impressora3',              # 👈 Novo ID
        'ip': '192.168.0.50',            # 👈 Novo IP
        'community': 'oabce'              # 👈 Community SNMP
    },
]
```

### 4️⃣ Salve e reinicie o servidor

**Pronto!** ✅ A nova impressora será automaticamente monitorada!

---

## Campos Explicados

| Campo | Exemplo | Descrição |
|-------|---------|-----------|
| `id` | `impressora3` | Identificador único (impressora1, impressora2, ...) |
| `ip` | `192.168.0.50` | IP interno da impressora |
| `community` | `oabce` | String SNMP (verifique na impressora) |

**Nota:** O nome da impressora é coletado automaticamente via SNMP (OID)

---

## Exemplo Completo (4 Impressoras)

```python
IMPRESSORAS_CONFIG = [
    {
        'id': 'impressora1',
        'ip': '192.168.0.39',
        'community': 'oabce'
    },
    {
        'id': 'impressora2',
        'ip': '192.168.0.32',
        'community': 'oabce'
    },
    {
        'id': 'impressora3',
        'ip': '192.168.0.50',
        'community': 'oabce'
    },
    {
        'id': 'impressora4',
        'ip': '192.168.0.51',
        'community': 'oabce'
    },
]
```

---

## ✅ O que acontece automaticamente

Quando você adiciona uma impressora:

1. ✅ Thread de monitoramento é criada
2. ✅ Nome é coletado via SNMP
3. ✅ Dados são coletados a cada 5 segundos
4. ✅ API retorna informações da impressora
5. ✅ Página HTML exibe automaticamente (se houver espaço)
6. ✅ Terminal mostra status com o nome da impressora

---

## 📝 Notas Importantes

- **ID deve ser único**: `impressora1`, `impressora2`, `impressora3`, etc.
- **IPs devem ser válidos**: Verifique no painel de controle da impressora
- **Community SNMP**: Geralmente é `public` ou `oabce` (configure na impressora)
- **Máximo recomendado**: 5-10 impressoras (por questão de performance)
- **Nome automático**: O nome é coletado via SNMP, não precisa configurar manualmente

---

## 🆙 Atualizar HTML para mais impressoras

O HTML atualmente suporta **3 colunas**. Se você adicionar mais de 3 impressoras:

1. Abra `frontend/templates/index.html`
2. Copie e cole um bloco `<!-- COLUNA N -->` e altere os IDs
3. Atualize o JavaScript para incluir os novos IDs

**Exemplo** (para impressora4):
```html
<!-- COLUNA 4 - IMPRESSORA -->
<div class="printer-column">
    <!-- CARD IMAGEM -->
    <div class="card printer">
        <div class="printer-image">
            <img src="/static/OKI_CALLCENTER.jpeg" alt="Impressora OKI">
        </div>
    </div>

    <!-- CARD NOME -->
    <div class="card">
        <div class="card-header">
            <h2 id="nome4">Carregando...</h2>
            <div class="status offline" id="status4">OFFLINE</div>
        </div>
    </div>
    ...
</div>
```

E no JavaScript:
```javascript
{ impressora: 'impressora4', status: 'status4', nome: 'nome4', mac: 'mac4', serial: 'serial4', descricao: 'descricao4', uptime: 'uptime4', impressoes: 'impressoes4', toner: 'toner4', scanner: 'scanner4' }
```
