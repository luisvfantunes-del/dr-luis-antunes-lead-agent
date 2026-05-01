# Agente de Leads - MVP

Este e o primeiro prototipo local do agente para leads que chegam a `info@drluisantunes.pt`.

## O que faz nesta fase

- Liga ao email por IMAP.
- Le mensagens recentes da caixa de entrada.
- Extrai dados provaveis da lead:
  - nome;
  - telefone;
  - email;
  - procedimento/mensagem;
  - origem tecnica quando existir.
- Recomenda o canal de resposta:
  - WhatsApp quando ha telefone;
  - email quando nao ha telefone.
- Cria uma fila de revisao em `lead_agent/data/pending_leads.jsonl`.

## O que ainda nao faz

- Nao envia mensagens sozinho.
- Nao marca consultas.
- Nao entra no IMED.
- Nao valida pagamentos.
- Nao atualiza automaticamente o Excel final.

Estas partes entram depois de validarmos a leitura das leads.

## Configuracao

1. Criar uma copia de `.env.example` chamada `.env`.
2. Colocar a password real no `.env`.
3. Nao partilhar nem enviar o ficheiro `.env`.

## Comando

```bash
python3 lead_agent/lead_agent.py fetch --limit 20
```

Para ver a fila:

```bash
python3 lead_agent/lead_agent.py show
```

Para abrir uma lead no WhatsApp Web com a mensagem preparada:

```bash
python3 lead_agent/lead_agent.py whatsapp 1
```

O numero `1` corresponde ao numero da lead mostrado no comando `show`.

## WhatsApp API

Esta e a via oficial/robusta para o agente enviar e receber mensagens.

Neste projeto, a opcao recomendada e `360dialog`, porque suporta coexistencia: o mesmo numero continua na app WhatsApp Business e tambem fica disponivel por API.

Antes de enviar mensagens reais com 360dialog e preciso preencher no `.env`:

- `WHATSAPP_PROVIDER=360dialog`
- `D360_API_KEY`
- `WHATSAPP_VERIFY_TOKEN`

O custo esperado e uma licenca mensal por numero na 360dialog, mais eventuais custos de mensagens cobrados pela Meta quando a mensagem sai pela API. Mensagens enviadas diretamente na app WhatsApp Business continuam a ser gratuitas.

### Verificar configuracao

```bash
python3 lead_agent/lead_agent.py api-check
```

### Testar payload sem enviar

```bash
python3 lead_agent/lead_agent.py api-send 1
```

### Enviar mensagem livre

```bash
python3 lead_agent/lead_agent.py api-send 1 --confirm
```

Nota: mensagens livres normalmente so funcionam dentro da janela de conversa permitida pela Meta. Para iniciar conversa com uma pessoa que ainda nao falou com o numero via API, pode ser necessario usar template aprovado.

### Testar template sem enviar

```bash
python3 lead_agent/lead_agent.py api-template 1 --template nome_do_template --language pt_PT
```

### Enviar template aprovado

```bash
python3 lead_agent/lead_agent.py api-template 1 --template nome_do_template --language pt_PT --confirm
```

### Webhook local

```bash
python3 lead_agent/lead_agent.py webhook --port 8080
```

Para producao, o webhook tem de estar num URL publico com HTTPS. Em local, pode ser exposto temporariamente com uma ferramenta tipo ngrok/Cloudflare Tunnel.

### Configurar webhook na 360dialog

Depois de teres um URL publico HTTPS:

```bash
python3 lead_agent/lead_agent.py api-set-webhook https://exemplo.com/webhook
```

Para configurar de verdade:

```bash
python3 lead_agent/lead_agent.py api-set-webhook https://exemplo.com/webhook --confirm
```

## Regra de canal

Se houver telefone valido, o agente recomenda WhatsApp. Se nao houver telefone, recomenda email.

Na fase inicial, a resposta sugerida deve ser aprovada manualmente.
