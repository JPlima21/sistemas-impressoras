from ipaddress import ip_address
import re

from services.historico_service import (
    carregar_configs_impressoras,
    excluir_config_impressora,
    salvar_config_impressora,
)

TOKEN_VALORES = {
    "nenhum": 0.00,
    "pb": 0.04,
    "colorida": 0.50,
}
ID_IMPRESSORA_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


class PrinterConfigService:
    # Guarda o contexto de banco usado pelas operações de configuração
    def __init__(self, caminho_banco):
        self.caminho_banco = caminho_banco

    # Padroniza os dados recebidos da tela/API antes de validar ou salvar
    def _normalizar_config(self, config):
        token_tipo = str(config.get("token_tipo") or config.get("token") or "pb").strip().lower()

        return {
            "id": str(config.get("id") or "").strip(),
            "ip": str(config.get("ip") or "").strip(),
            "community": str(config.get("community") or "").strip(),
            "token_tipo": token_tipo,
        }

    # Valida campos obrigatórios, token e duplicidade de id/IP
    def _validar_config(self, config, configs_existentes=None):
        if not config["id"]:
            raise ValueError("Informe um identificador para a impressora.")
        if not ID_IMPRESSORA_PATTERN.fullmatch(config["id"]):
            raise ValueError("Use apenas letras, numeros, ponto, hifen ou underline no identificador.")
        if not config["ip"]:
            raise ValueError("Informe o IP da impressora.")
        try:
            ip_address(config["ip"])
        except ValueError as exc:
            raise ValueError("Informe um IP valido para a impressora.") from exc
        if not config["community"]:
            raise ValueError("Informe a community SNMP da impressora.")
        if len(config["community"]) > 255:
            raise ValueError("A community SNMP deve ter no maximo 255 caracteres.")
        if config["token_tipo"] not in TOKEN_VALORES:
            raise ValueError("Informe um token valido para a impressora.")

        existentes = configs_existentes or []
        for existente in existentes:
            if existente["id"].lower() == config["id"].lower():
                raise ValueError(f"Ja existe uma impressora com o identificador '{config['id']}'.")
            if existente["ip"] == config["ip"]:
                raise ValueError(f"Ja existe uma impressora cadastrada com o IP {config['ip']}.")

    # Gera automaticamente o próximo identificador livre no padrão impressoraN
    def _gerar_proximo_id(self, configs):
        indice = 1
        ids_existentes = {str(config.get("id") or "").lower() for config in configs}

        while f"impressora{indice}" in ids_existentes:
            indice += 1

        return f"impressora{indice}"

    # Lista as configurações de impressoras salvas no banco
    def list_configs(self):
        return carregar_configs_impressoras(self.caminho_banco)

    # Prepara uma nova configuração, gerando id automático quando ele não foi informado
    def preparar_nova_config(self, dados):
        configs = self.list_configs()
        config = self._normalizar_config(dados)

        if not config["id"]:
            config["id"] = self._gerar_proximo_id(configs)

        self._validar_config(config, configs_existentes=configs)
        return config

    # Cria uma nova impressora a partir dos dados brutos recebidos pela API
    def add_config(self, dados):
        config = self.preparar_nova_config(dados)
        return self.save_config(config)

    # Salva uma configuração já preparada e validada no banco
    def save_config(self, config):
        configs = self.list_configs()
        config_normalizada = self._normalizar_config(config)
        self._validar_config(config_normalizada, configs_existentes=configs)
        salvar_config_impressora(self.caminho_banco, config_normalizada)
        return dict(config_normalizada)

    # Exclui a configuração de uma impressora existente
    def delete_config(self, impressora_id):
        impressora_id = str(impressora_id or "").strip()
        if not impressora_id:
            raise ValueError("Informe a impressora que deseja excluir.")

        existentes = self.list_configs()
        if not any(item["id"] == impressora_id for item in existentes):
            raise ValueError("Impressora nao encontrada.")

        excluir_config_impressora(self.caminho_banco, impressora_id)
