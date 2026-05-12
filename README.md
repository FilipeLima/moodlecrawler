# AVA Crawler com GitHub Actions + Telegram

Este projeto automatiza acessos ao AVA utilizando Python, `requests.Session()` e GitHub Actions.

O sistema:

- realiza login automaticamente;
- acessa URLs das disciplinas;
- executa verificações;
- possui retry automático em caso de falha;
- envia relatórios no Telegram;
- roda automaticamente uma vez por dia na nuvem gratuitamente.

---

# Estrutura do Projeto

```text
.
├── crawler.py
├── requirements.txt
└── .github
    └── workflows
        └── crawler.yml
```

---

# Tutorial — Criando o Repositório

## 1. Criar conta no GitHub

Acesse:

https://github.com

Crie sua conta gratuitamente.

---

## 2. Criar um novo repositório

Clique em:

```text
New Repository
```

Escolha um nome, por exemplo:

```text
ava-crawler
```

Marque:

```text
Public
```

ou:

```text
Private
```

Clique em:

```text
Create Repository
```

---

# Tutorial — Configurando o GitHub Actions

O GitHub Actions permite executar scripts automaticamente na nuvem.

---

## 1. Criar pasta do workflow

Dentro do repositório crie:

```text
.github/workflows/
```

---

## 2. Criar o arquivo crawler.yml

Caminho:

```text
.github/workflows/crawler.yml
```

Conteúdo:

```yaml
name: AVA Crawler

on:

  # executa automaticamente todos os dias
  schedule:
    - cron: '0 10 * * *'

  # permite executar manualmente
  workflow_dispatch:

jobs:

  crawler:

    runs-on: ubuntu-latest

    steps:

      # baixa os arquivos do repositório
      - uses: actions/checkout@v4

      # instala Python
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      # instala bibliotecas
      - name: Instalar dependências
        run: |
          pip install -r requirements.txt

      # executa o crawler
      - name: Executar crawler
        env:
          USUARIO: ${{ secrets.USUARIO }}
          SENHA: ${{ secrets.SENHA }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}

        run: |
          python crawler.py
```

---

# Explicação do crawler.yml

## schedule

```yaml
schedule:
  - cron: '0 10 * * *'
```

Executa diariamente às 10:00 UTC.

---

## workflow_dispatch

Permite executar manualmente pela interface do GitHub.

---

## runs-on

```yaml
runs-on: ubuntu-latest
```

Cria uma máquina Linux temporária.

---

## actions/checkout

Baixa os arquivos do repositório.

---

## setup-python

Instala o Python automaticamente.

---

## pip install

Instala as dependências do projeto.

---

## env

Passa variáveis secretas para o Python.

---

# Configurando os Secrets do GitHub

No repositório:

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

Criar os seguintes secrets:

| Nome | Descrição |
|---|---|
| USUARIO | Login do AVA |
| SENHA | Senha do AVA |
| TELEGRAM_TOKEN | Token do bot |
| TELEGRAM_CHAT_ID | ID do chat |

---

# Tutorial — Criando o Bot do Telegram

---

## 1. Abrir o BotFather

No Telegram procure:

```text
@BotFather
```

ou acesse:

https://t.me/BotFather

---

## 2. Criar um novo bot

Enviar:

```text
/newbot
```

O BotFather pedirá:

- nome do bot;
- username do bot.

Exemplo:

```text
Nome: AVA Crawler
Username: ava_crawler_bot
```

---

## 3. Copiar o TOKEN

O BotFather retornará algo como:

```text
123456789:ABCDEFxxxxxxxxxxxxxxxx
```

Esse é o:

```text
TELEGRAM_TOKEN
```

---

# Obtendo o TELEGRAM_CHAT_ID

---

## 1. Abrir conversa com o bot

Procure seu bot no Telegram.

Envie:

```text
/start
```

---

## 2. Descobrir o chat_id

Abra no navegador:

```text
https://api.telegram.org/botSEU_TOKEN/getUpdates
```

Substitua:

```text
SEU_TOKEN
```

pelo token real.

---

## 3. Encontrar o ID

Você verá algo parecido com:

```json
{
  "chat": {
    "id": 123456789
  }
}
```

O número:

```text
123456789
```

é o:

```text
TELEGRAM_CHAT_ID
```

---

# Arquivo requirements.txt

Criar:

```text
requirements.txt
```

Conteúdo:

```text
requests
beautifulsoup4
python-telegram-bot
tenacity
```

---

# Código do crawler.py

```python
import os
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed
from telegram import Bot

# ==========================================
# CONFIGURAÇÕES
# ==========================================

USUARIO = os.environ["USUARIO"]
SENHA = os.environ["SENHA"]

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

LOGIN_URL = "https://ava.ead.ifsertaope.edu.br/login/index.php?loginredirect=1"

disciplinas = [921, 920, 919, 918, 917]

# ==========================================
# TELEGRAM
# ==========================================

async def enviar_telegram(mensagem):

    bot = Bot(token=TELEGRAM_TOKEN)

    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=mensagem
    )

# ==========================================
# RETRY AUTOMÁTICO
# ==========================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(10)
)
def acessar_url(sessao, url):

    response = sessao.get(url, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Erro {response.status_code}")

    return response

# ==========================================
# LOGIN
# ==========================================

def fazer_login():

    sessao = requests.Session()

    resposta = sessao.get(LOGIN_URL)

    soup = BeautifulSoup(resposta.text, "html.parser")

    logintoken = soup.find("input", {"name": "logintoken"})

    payload = {
        "username": USUARIO,
        "password": SENHA
    }

    if logintoken:
        payload["logintoken"] = logintoken["value"]

    login = sessao.post(LOGIN_URL, data=payload)

    if "loginerrormessage" in login.text:
        raise Exception("Falha no login")

    return sessao

# ==========================================
# EXECUÇÃO PRINCIPAL
# ==========================================

async def main():

    relatorio = []

    try:

        sessao = fazer_login()

        relatorio.append("✅ Login realizado com sucesso.")

        for i in disciplinas:

            relatorio.append(f"\n📚 Disciplina {i}")

            urls = [
                f"https://ava.ead.ifsertaope.edu.br/course/view.php?id={i}",
                f"https://ava.ead.ifsertaope.edu.br/user/index.php?id={i}",
                f"https://ava.ead.ifsertaope.edu.br/user/index.php?id={i}&tsort=lastaccess&tdir=4",
                f"https://ava.ead.ifsertaope.edu.br/grade/report/grader/index.php?id={i}",
                f"https://ava.ead.ifsertaope.edu.br/report/log/index.php?chooselog=1&showusers=0&showcourses=0&id={i}&group=3168&user=&date=&modid=&modaction=&origin=&edulevel=-1&logreader=logstore_standard"
            ]

            for url in urls:

                try:

                    acessar_url(sessao, url)

                    relatorio.append(f"✔ {url}")

                except Exception as erro:

                    relatorio.append(f"❌ {url}")
                    relatorio.append(str(erro))

        mensagem = "\n".join(relatorio)

        await enviar_telegram(mensagem)

    except Exception as erro_geral:

        await enviar_telegram(
            f"🚨 ERRO GERAL NO CRAWLER\n\n{str(erro_geral)}"
        )

# ==========================================
# INÍCIO
# ==========================================

if __name__ == "__main__":

    import asyncio

    asyncio.run(main())
```

---

# Explicação do crawler.py

---

## requests.Session()

```python
sessao = requests.Session()
```

Mantém cookies e autenticação entre requisições.

---

## BeautifulSoup

```python
BeautifulSoup(resposta.text, "html.parser")
```

Permite extrair o token de login da página HTML.

---

## Retry automático

```python
@retry(stop=stop_after_attempt(3))
```

Caso uma requisição falhe, o sistema tenta novamente.

---

## Telegram

```python
await bot.send_message()
```

Envia mensagens automaticamente.

---

## Variáveis de ambiente

```python
os.environ["USUARIO"]
```

Evita expor senhas no código.

---

## Loop das disciplinas

```python
for i in disciplinas:
```

Executa o processo para cada disciplina.

---

# Executando Manualmente

No GitHub:

```text
Actions
→ AVA Crawler
→ Run workflow
```

---

# Logs da Execução

Os logs podem ser visualizados em:

```text
Actions
→ Selecionar execução
```

---

# Possíveis Melhorias Futuras

- download automático de CSV;
- integração com Google Sheets;
- dashboard web;
- geração de relatórios PDF;
- notificações condicionais;
- paralelização das disciplinas;
- banco de dados SQLite;
- Docker;
- execução assíncrona com aiohttp;
- gráficos automáticos;
- envio de arquivos pelo Telegram.

---

# Licença

Projeto para fins educacionais e automação pessoal.
