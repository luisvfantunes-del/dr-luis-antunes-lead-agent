# Deploy estavel no Render

Objetivo: ter um webhook publico e estavel para a 360dialog, sem depender do Mac nem de tuneis temporarios.

## Porque Render

- Da URL publico HTTPS automaticamente.
- Mantem o agente online num servidor.
- Permite custom domain depois, por exemplo `agent.drluisantunes.pt`.
- E simples para este primeiro webhook.

## Custo

Usar um plano pago simples para o webhook nao adormecer. Evitar plano gratuito para WhatsApp, porque pode dormir e falhar mensagens.

## Passos

1. Criar conta em https://render.com/
2. Criar um novo Web Service a partir deste projeto/repositório.
3. Se o Render detetar `render.yaml`, escolher o serviço `dr-luis-antunes-lead-agent`.
4. Definir environment variables secretas:

```env
D360_API_KEY=...
WHATSAPP_VERIFY_TOKEN=...
```

5. Deploy.
6. Abrir o URL publico que o Render gerar, por exemplo:

```text
https://dr-luis-antunes-lead-agent.onrender.com/health
```

Deve responder:

```text
OK
```

7. Configurar a 360dialog com:

```bash
python3 lead_agent/lead_agent.py api-set-webhook https://dr-luis-antunes-lead-agent.onrender.com/webhook --confirm
```

## Depois

Quando o webhook estiver estavel, podemos ligar um dominio bonito:

```text
https://agent.drluisantunes.pt/webhook
```

Para isso e preciso configurar DNS no sitio onde o dominio e gerido.
