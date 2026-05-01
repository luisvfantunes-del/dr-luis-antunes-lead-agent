# 360dialog setup

Objetivo: ligar o numero atual do WhatsApp Business a API mantendo coexistencia.

## Porque 360dialog

- Permite WhatsApp Coexistence: app WhatsApp Business + API no mesmo numero.
- As mensagens enviadas pela API aparecem na app.
- As mensagens enviadas pela app podem chegar ao agente via webhook.
- E mais simples para integrar com um agente proprio do que uma plataforma de inbox completa.

## Links

- Signup/API: https://360dialog.com/whatsapp-api
- Coexistence: https://docs.360dialog.com/docs/resources/phone-numbers/coexistence
- Pricing: https://360dialog.com/pricing/

## Passos

1. Criar conta na 360dialog.
2. Escolher WhatsApp API / Regular.
3. No onboarding, escolher a opcao de coexistencia ou ligar numero existente da WhatsApp Business app.
4. No telemovel, em WhatsApp Business > Business Platform, inserir o codigo ou ler o QR gerado pela 360dialog.
5. Confirmar que o numero fica ativo no Client Hub.
6. Copiar a API key do canal/numero.
7. Colocar a API key no ficheiro `.env`:

```env
WHATSAPP_PROVIDER=360dialog
D360_API_KEY=...
D360_BASE_URL=https://waba-v2.360dialog.io
```

8. Testar configuracao:

```bash
python3 lead_agent/lead_agent.py api-check
```

9. Configurar webhook quando existir URL publico HTTPS:

```bash
python3 lead_agent/lead_agent.py api-set-webhook https://dominio.pt/webhook --confirm
```

## Notas importantes

- Nao apagar a app WhatsApp Business.
- Abrir a app pelo menos uma vez a cada 13 dias para manter a conta ativa.
- Mensagens enviadas pela app continuam gratis.
- Mensagens enviadas pela API podem ter custo Meta.
- Para iniciar conversa pela API, normalmente e preciso template aprovado.
- Dentro da janela de 24h apos resposta do paciente, o agente pode enviar texto livre.
