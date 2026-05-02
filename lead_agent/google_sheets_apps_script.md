# Google Sheets - ponte para o agente de leads

Este script cria um endpoint simples para o Render escrever no Google Sheets.

## 1. Criar a folha

1. Abre [Google Sheets](https://sheets.google.com).
2. Cria uma folha nova, por exemplo `Funil Leads Dr Luis Antunes`.
3. Renomeia o primeiro separador para `Leads`.

## 2. Abrir o Apps Script

No Google Sheets:

`Extensões` -> `Apps Script`

Se ao carregar em `Apps Script` aparecer uma página do Google Drive a dizer que não é possível abrir o ficheiro, usa a alternativa robusta:

1. Abre [https://script.new](https://script.new).
2. Cria o script aí.
3. No Google Sheet, copia o ID da folha a partir do URL.

Exemplo:

```text
https://docs.google.com/spreadsheets/d/1ABCDEF123456789/edit
```

O ID é:

```text
1ABCDEF123456789
```

Depois cola esse ID na constante `SPREADSHEET_ID` no código abaixo.

Apaga o código que aparece e cola este:

```javascript
const SHEET_NAME = 'Leads';
const SECRET = 'TROCAR_POR_UM_SEGREDO_FORTE';
const SPREADSHEET_ID = ''; // preencher se usares https://script.new

const HEADERS = [
  'Estado',
  'Dias no estado',
  'Data Entrada',
  'Nome',
  'Telefone',
  'Email',
  'Interesse',
  'Origem',
  'Canal',
  'Última mensagem',
  'Última interação',
  'Approval ID',
  'Message ID',
  'Notas'
];

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents || '{}');
    if (body.secret !== SECRET) {
      return jsonResponse({ ok: false, error: 'unauthorized' }, 403);
    }

    const action = body.action;
    const payload = body.payload || {};
    const sheet = getLeadsSheet_();

    if (action === 'upsert_lead') {
      upsertLead_(sheet, payload);
      return jsonResponse({ ok: true, action });
    }

    if (action === 'mark_contacted') {
      markContacted_(sheet, payload);
      return jsonResponse({ ok: true, action });
    }

    return jsonResponse({ ok: false, error: 'unknown_action' }, 400);
  } catch (error) {
    return jsonResponse({ ok: false, error: String(error) }, 500);
  }
}

function doGet() {
  return jsonResponse({
    ok: true,
    message: 'Google Sheets webhook ativo'
  });
}

function getLeadsSheet_() {
  const spreadsheet = SPREADSHEET_ID
    ? SpreadsheetApp.openById(SPREADSHEET_ID)
    : SpreadsheetApp.getActiveSpreadsheet();
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(SHEET_NAME);
  }

  const currentHeaders = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
  const needsHeaders = currentHeaders.join('') === '' || currentHeaders[0] !== HEADERS[0];
  if (needsHeaders) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, HEADERS.length)
      .setBackground('#12344d')
      .setFontColor('#ffffff')
      .setFontWeight('bold');
  }
  return sheet;
}

function upsertLead_(sheet, payload) {
  const rowIndex = findRow_(sheet, payload.telefone, payload.message_id);
  const now = parseDate_(payload.ultima_interacao);
  const entrada = parseDate_(payload.data_entrada);
  const row = [
    payload.estado || 'Aguardando validação',
    '',
    entrada,
    payload.nome || '',
    payload.telefone || '',
    payload.email || '',
    payload.interesse || '',
    payload.origem || '',
    payload.canal || '',
    payload.ultima_mensagem || '',
    now,
    payload.approval_id || '',
    payload.message_id || '',
    payload.notas || ''
  ];

  if (rowIndex) {
    sheet.getRange(rowIndex, 1, 1, row.length).setValues([row]);
  } else {
    sheet.insertRowAfter(1);
    sheet.getRange(2, 1, 1, row.length).setValues([row]);
  }

  formatSheet_(sheet);
}

function markContacted_(sheet, payload) {
  const rowIndex = findRow_(sheet, payload.telefone, payload.message_id);
  if (!rowIndex) {
    return;
  }
  sheet.getRange(rowIndex, 1).setValue(payload.estado || 'Aguardando resposta');
  sheet.getRange(rowIndex, 11).setValue(parseDate_(payload.ultima_interacao));
  if (payload.approval_id) {
    sheet.getRange(rowIndex, 12).setValue(payload.approval_id);
  }
  formatSheet_(sheet);
}

function findRow_(sheet, telefone, messageId) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return 0;
  }

  const values = sheet.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
  const targetPhone = normalisePhone_(telefone);
  for (let i = 0; i < values.length; i++) {
    const rowPhone = normalisePhone_(values[i][4]);
    const rowMessageId = String(values[i][12] || '');
    if (messageId && rowMessageId === messageId) {
      return i + 2;
    }
    if (targetPhone && rowPhone === targetPhone) {
      return i + 2;
    }
  }
  return 0;
}

function formatSheet_(sheet) {
  const lastRow = Math.max(sheet.getLastRow(), 2);
  sheet.getRange(2, 2, lastRow - 1, 1).setFormulaR1C1('=IF(RC[9]="","",TODAY()-INT(RC[9]))');
  sheet.getRange(2, 3, lastRow - 1, 1).setNumberFormat('dd/mm/yy');
  sheet.getRange(2, 11, lastRow - 1, 1).setNumberFormat('dd/mm/yy hh:mm');
  sheet.getRange(1, 1, lastRow, HEADERS.length).setWrap(true).setVerticalAlignment('middle');
  sheet.setColumnWidths(1, 1, 170);
  sheet.setColumnWidths(2, 1, 95);
  sheet.setColumnWidths(3, 1, 105);
  sheet.setColumnWidths(4, 1, 180);
  sheet.setColumnWidths(5, 1, 140);
  sheet.setColumnWidths(6, 1, 220);
  sheet.setColumnWidths(7, 1, 210);
  sheet.setColumnWidths(10, 1, 360);
  sheet.setColumnWidths(14, 1, 260);
  applyStatusColors_(sheet, lastRow);
}

function applyStatusColors_(sheet, lastRow) {
  const range = sheet.getRange(2, 1, Math.max(lastRow - 1, 1), HEADERS.length);
  const rules = [
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains('Consulta confirmada')
      .setBackground('#d9ead3')
      .setRanges([range])
      .build(),
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains('Aguardando pagamento')
      .setBackground('#fff2cc')
      .setRanges([range])
      .build(),
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains('Aguardando resposta')
      .setBackground('#d9eaf7')
      .setRanges([range])
      .build(),
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains('Aguardando validação')
      .setBackground('#eadcf8')
      .setRanges([range])
      .build()
  ];
  sheet.setConditionalFormatRules(rules);
}

function parseDate_(value) {
  if (!value) {
    return new Date();
  }
  const date = new Date(value);
  if (isNaN(date.getTime())) {
    return new Date();
  }
  return date;
}

function normalisePhone_(value) {
  return String(value || '').replace(/\D/g, '');
}

function jsonResponse(data, statusCode) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
```

## 3. Publicar como Web App

1. Carrega em `Implementar` / `Deploy`.
2. Escolhe `Nova implementação`.
3. Tipo: `Aplicação Web`.
4. Executar como: `Eu`.
5. Quem tem acesso: `Qualquer pessoa`.
6. Carrega `Implementar`.
7. Copia o URL da aplicação Web.

## 4. Variáveis no Render

No Render, em `Environment`, adicionar:

```text
GOOGLE_SHEETS_WEBHOOK_URL=<URL da aplicação Web>
GOOGLE_SHEETS_WEBHOOK_SECRET=<o mesmo segredo colocado em SECRET>
```

Depois faz `Manual Deploy`.
