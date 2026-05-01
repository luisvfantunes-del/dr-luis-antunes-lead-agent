# Testar webhook com tunnel temporario

O ambiente do Codex pode bloquear portas locais. Para testar no Mac normal, abrir dois Terminais.

## Terminal 1: arrancar o webhook local

```bash
cd "/Users/lantunes/Documents/New project"
python3 lead_agent/lead_agent.py webhook --host 127.0.0.1 --port 8080
```

Deve aparecer:

```text
Webhook WhatsApp a escutar em http://127.0.0.1:8080/webhook
```

## Terminal 2: criar URL publico temporario

```bash
ssh -o ServerAliveInterval=60 -R 80:localhost:8080 nokey@localhost.run
```

Se perguntar:

```text
Are you sure you want to continue connecting?
```

Responder:

```text
yes
```

O tunnel deve mostrar um URL publico HTTPS. Copiar o URL e acrescentar `/webhook`.

Exemplo:

```text
https://exemplo.lhr.life/webhook
```

## Configurar na 360dialog

Depois de confirmar o URL comigo, eu configuro na 360dialog com:

```bash
python3 lead_agent/lead_agent.py api-set-webhook https://exemplo.lhr.life/webhook --confirm
```

## Nota

Este tunnel e temporario. Quando fechar o Terminal 2, o URL deixa de funcionar. Para producao, usar subdominio fixo, por exemplo:

```text
https://agent.drluisantunes.pt/webhook
```
