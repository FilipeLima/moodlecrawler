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

    # pega token/cookies iniciais
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
