# WhatsApp Cloud API - Setup

## Objetivo

Ligar o agente ao WhatsApp Cloud API oficial da Meta para enviar mensagens WhatsApp a leads, depois de aprovacao humana.

## O que precisa existir na Meta

### 1. Meta Business Manager

Precisas de uma conta Business Manager da clinica.

Idealmente:

- negocio verificado;
- acesso de administrador;
- metodo de pagamento configurado.

### 2. App Meta Developers

Criar uma app em:

https://developers.facebook.com/apps/

Tipo de app:

- Business

Produto a adicionar:

- WhatsApp

### 3. WhatsApp Business Account

Dentro da app/Meta Business, precisa existir uma WhatsApp Business Account.

Dados que vamos precisar:

- `WHATSAPP_BUSINESS_ACCOUNT_ID`
- `WHATSAPP_PHONE_NUMBER_ID`

### 4. Numero de telefone

Para API oficial, a Meta precisa de um numero ligado ao WhatsApp Cloud API.

Importante:

- se o numero estiver a ser usado na app WhatsApp Business normal, pode nao poder ser usado em simultaneo na API;
- a solucao mais segura e usar um numero dedicado para API;
- se quiseres usar o numero atual, temos de confirmar se a Meta permite migracao sem perder o uso operacional que tens hoje.

### 5. Access token

Para testes, a Meta gera um token temporario.

Para producao, precisamos de um token permanente via System User no Business Manager.

Guardar no `.env`:

```env
WHATSAPP_ACCESS_TOKEN=...
```

### 6. Webhook

O webhook serve para receber:

- mensagens recebidas;
- estados de entrega;
- erros;
- eventos de conversa.

No `.env` ja existe:

```env
WHATSAPP_VERIFY_TOKEN=dr_luis_antunes_webhook_verify_token
```

Este token tem de ser igual ao configurado na Meta.

Para producao, precisamos de um URL publico HTTPS. Exemplos:

- dominio proprio;
- Cloudflare Tunnel;
- ngrok para testes.

### 7. Templates aprovados

Para iniciar conversa com uma lead que veio do formulario, normalmente temos de usar template aprovado.

Criar pelo menos estes templates:

## Template 1 - consulta inicial PT

Nome sugerido:

`consulta_inicial_pt`

Categoria:

Utility

Idioma:

Portuguese

Texto:

```text
Olá {{1}}, sou a Cátia Correia, assistente pessoal do Dr. Luís Antunes.

Recebemos o seu pedido de contacto. Podemos agendar uma consulta com o Dr. Antunes para discutir o seu caso. A consulta pode ser presencial em Lisboa ou por videochamada. O valor é de 150€.

Tem preferência de datas ou horário?
```

Parametro:

- `{{1}}` = primeiro nome

## Template 2 - consulta inicial EN

Nome sugerido:

`consulta_inicial_en`

Categoria:

Utility

Idioma:

English

Texto:

```text
Hello {{1}}, my name is Cátia Correia, personal assistant to Dr. Luís Antunes.

We received your contact request. Dr. Antunes would be happy to see you for a consultation to discuss your case. The consultation can be in person at our clinic in Lisbon or via video call. The consultation fee is €150.

Do you have a preference or any specific dates in mind?
```

Parametro:

- `{{1}}` = first name

## O que ja esta feito localmente

O agente ja tem:

- leitura de email por IMAP;
- extracao de lead;
- fila de revisao;
- normalizacao de telefone;
- comando de WhatsApp Web assistido;
- cliente de WhatsApp Cloud API;
- comando para mensagem livre;
- comando para template;
- servidor local de webhook.

## O que falta preencher no `.env`

```env
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_BUSINESS_ACCOUNT_ID=...
```

## Comandos

Verificar configuracao:

```bash
python3 lead_agent/lead_agent.py api-check
```

Testar payload de mensagem livre sem enviar:

```bash
python3 lead_agent/lead_agent.py api-send 1
```

Enviar mensagem livre:

```bash
python3 lead_agent/lead_agent.py api-send 1 --confirm
```

Testar template sem enviar:

```bash
python3 lead_agent/lead_agent.py api-template 1 --template consulta_inicial_pt --language pt_PT
```

Enviar template:

```bash
python3 lead_agent/lead_agent.py api-template 1 --template consulta_inicial_pt --language pt_PT --confirm
```

