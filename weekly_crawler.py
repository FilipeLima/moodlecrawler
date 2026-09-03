import io
import os
import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed


# ============================================================
# CONFIGURAÇÕES
# ============================================================

USUARIO = os.environ["USUARIO"]
SENHA = os.environ["SENHA"]

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

LOGIN_URL = (
    "https://ava.ead.ifsertaope.edu.br/login/index.php"
    "?loginredirect=1"
)

# Altere posteriormente os IDs das disciplinas e dos grupos.
# Formato: ID_DA_DISCIPLINA: ID_DO_GRUPO
DISCIPLINAS = {
    921: 3168,
    920: 3168,
    919: 3168,
    918: 3168,
    917: 3168,
}

DELAY_ENTRE_ACESSOS = 5


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(mensagem):
    """Envia uma mensagem de texto pelo bot do Telegram."""

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    resposta = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mensagem,
        },
        timeout=30,
    )

    resposta.raise_for_status()


def enviar_arquivo_telegram(
    conteudo,
    nome_arquivo,
    legenda,
):
    """Envia um arquivo pelo bot do Telegram."""

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"

    arquivo = io.BytesIO(conteudo)
    arquivo.name = nome_arquivo

    resposta = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": legenda,
        },
        files={
            "document": (
                nome_arquivo,
                arquivo,
                "text/csv",
            )
        },
        timeout=60,
    )

    resposta.raise_for_status()


# ============================================================
# ACESSO HTTP COM RETRY
# ============================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(20),
    reraise=True,
)
def acessar_url(sessao, url):
    """Acessa uma URL e repete a tentativa em caso de falha."""

    resposta = sessao.get(
        url,
        timeout=30,
    )

    resposta.raise_for_status()

    return resposta


# ============================================================
# LOGIN
# ============================================================

def fazer_login():
    """Realiza o login e retorna a Session autenticada."""

    sessao = requests.Session()

    try:
        resposta = acessar_url(
            sessao,
            LOGIN_URL,
        )

        soup = BeautifulSoup(
            resposta.text,
            "html.parser",
        )

        logintoken = soup.find(
            "input",
            {"name": "logintoken"},
        )

        payload = {
            "username": USUARIO,
            "password": SENHA,
        }

        if logintoken:
            payload["logintoken"] = logintoken["value"]

        login = sessao.post(
            LOGIN_URL,
            data=payload,
            timeout=30,
        )

        login.raise_for_status()

        # O Moodle normalmente redireciona para a página inicial
        # após um login bem-sucedido.
        if "loginerrormessage" in login.text.lower():
            raise RuntimeError(
                "Usuário ou senha inválidos."
            )

        # Confirma que a sessão parece autenticada.
        # Caso o Moodle tenha redirecionado para login novamente,
        # consideramos o login malsucedido.
        if "/login/index.php" in login.url:
            raise RuntimeError(
                "O Moodle retornou à página de login. "
                "A autenticação não foi concluída."
            )

        return sessao

    except Exception:
        raise


# ============================================================
# OBTENÇÃO DO SESSKEY
# ============================================================

def obter_sesskey(sessao, disciplina):
    """
    Acessa a página do relatório e procura o sesskey no HTML.

    O sesskey não deve ser fixado no código, pois pertence à sessão
    autenticada e pode mudar.
    """

    url_relatorio = (
        "https://ava.ead.ifsertaope.edu.br/report/log/index.php"
        f"?chooselog=1"
        f"&showusers=0"
        f"&showcourses=0"
        f"&id={disciplina}"
        f"&group={DISCIPLINAS[disciplina]}"
        f"&user="
        f"&date="
        f"&modid="
        f"&modaction="
        f"&origin="
        f"&edulevel=-1"
        f"&logreader=logstore_standard"
    )

    resposta = acessar_url(
        sessao,
        url_relatorio,
    )

    soup = BeautifulSoup(
        resposta.text,
        "html.parser",
    )

    # Procura o sesskey em links, inputs e atributos comuns.
    candidatos = []

    for tag in soup.find_all(
        ["a", "form", "input"]
    ):
        for atributo in (
            "href",
            "action",
            "value",
        ):
            valor = tag.get(atributo)

            if valor and "sesskey=" in valor:
                candidatos.append(valor)

    for valor in candidatos:
        trecho = valor.split("sesskey=", 1)[1]
        sesskey = trecho.split("&", 1)[0]

        if sesskey:
            return sesskey

    raise RuntimeError(
        f"Não foi possível encontrar o sesskey "
        f"para a disciplina {disciplina}."
    )


# ============================================================
# DOWNLOAD DO CSV
# ============================================================

def baixar_csv(sessao, disciplina, sesskey):
    """
    Reproduz a requisição feita pelo botão Download CSV.

    A estrutura foi baseada na requisição cURL fornecida:
    download=csv, id, group, chooselog e logreader.
    """

    grupo = DISCIPLINAS[disciplina]

    url_csv = (
        "https://ava.ead.ifsertaope.edu.br/report/log/index.php"
        f"?sesskey={sesskey}"
        f"&download=csv"
        f"&id={disciplina}"
        f"&group={grupo}"
        f"&modid="
        f"&chooselog=1"
        f"&logreader=logstore_standard"
    )

    resposta = acessar_url(
        sessao,
        url_csv,
    )

    if not resposta.content:
        raise RuntimeError(
            f"O download da disciplina {disciplina} "
            "retornou um arquivo vazio."
        )

    return resposta.content


# ============================================================
# PROCESSAMENTO DO CSV
# ============================================================

def analisar_csv(conteudo_csv):
    """
    Reproduz a lógica principal do notebook:
    - converte Hora;
    - cria semanas;
    - conta ocorrências;
    - cria a tabela por aluno;
    - classifica como REGULAR, AUSENTE ou RISCO DE EVASÃO.
    """

    # O CSV exportado pelo Moodle pode conter BOM.
    df = pd.read_csv(
        io.BytesIO(conteudo_csv),
        encoding="utf-8-sig",
    )

    colunas_necessarias = {
        "Hora",
        "Nome completo",
    }

    faltantes = colunas_necessarias - set(df.columns)

    if faltantes:
        raise RuntimeError(
            "O CSV não possui as colunas esperadas: "
            + ", ".join(sorted(faltantes))
        )

    df["Hora"] = pd.to_datetime(
        df["Hora"],
        format="%d/%m/%y, %H:%M:%S",
    )

    df["Semana"] = (
        df["Hora"]
        .dt.to_period("W")
        .apply(lambda periodo: periodo.start_time)
    )

    tabela = (
        df
        .groupby(
            ["Semana", "Nome completo"]
        )
        .size()
        .reset_index(
            name="Ocorrências"
        )
    )

    tabela_pivot = (
        tabela
        .pivot(
            index="Nome completo",
            columns="Semana",
            values="Ocorrências",
        )
        .fillna(0)
    )

    tabela_pivot = tabela_pivot.sort_index(axis=1)
    tabela_pivot = tabela_pivot.astype(int)

    tabela_pivot.columns = [
        f"Semana {i + 1}"
        for i in range(
            len(tabela_pivot.columns)
        )
    ]

    def classificar_linha(linha):
        resultado = []

        for i, valor in enumerate(linha):

            if valor > 0:
                resultado.append("REGULAR")

            elif i == 0:
                resultado.append("AUSENTE")

            elif linha[i - 1] == 0:
                resultado.append(
                    "RISCO DE EVASÃO"
                )

            else:
                resultado.append("AUSENTE")

        return resultado

    tabela_status = pd.DataFrame(
        tabela_pivot.apply(
            lambda linha: classificar_linha(
                linha.values
            ),
            axis=1,
            result_type="expand",
        ).values,
        index=tabela_pivot.index,
        columns=tabela_pivot.columns,
    )

    tabela_status.index.name = "Nome completo"

    return tabela_status


# ============================================================
# PROCESSAMENTO DE UMA DISCIPLINA
# ============================================================

def processar_disciplina(
    sessao,
    disciplina,
    grupo,
):
    """Baixa, processa e retorna a tabela de uma disciplina."""

    print(
        f"\nProcessando disciplina {disciplina} "
        f"(grupo {grupo})..."
    )

    # Acessa a página do relatório e obtém o sesskey.
    sesskey = obter_sesskey(
        sessao,
        disciplina,
    )

    time.sleep(DELAY_ENTRE_ACESSOS)

    # Reproduz o botão Download CSV.
    conteudo_csv = baixar_csv(
        sessao,
        disciplina,
        sesskey,
    )

    time.sleep(DELAY_ENTRE_ACESSOS)

    # Processa o CSV.
    tabela = analisar_csv(
        conteudo_csv
    )

    return tabela


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    inicio = time.time()

    print("Iniciando crawler semanal...")

    try:
        sessao = fazer_login()

    except Exception as erro:
        mensagem = (
            "🚨 ERRO NO LOGIN DO CRAWLER SEMANAL\n\n"
            f"{erro}"
        )

        print(mensagem)

        try:
            enviar_telegram(mensagem)
        except Exception as erro_telegram:
            print(
                "Não foi possível enviar o alerta "
                f"ao Telegram: {erro_telegram}"
            )

        raise

    enviar_telegram(
        "▶️ Crawler semanal iniciado.\n"
        f"Disciplinas: {len(DISCIPLINAS)}"
    )

    sucessos = 0
    falhas = 0

    for disciplina, grupo in DISCIPLINAS.items():

        try:

            tabela = processar_disciplina(
                sessao,
                disciplina,
                grupo,
            )

            arquivo = io.BytesIO()

            tabela.to_csv(
                arquivo,
                encoding="utf-8-sig",
            )

            conteudo = arquivo.getvalue()

            nome_arquivo = (
                f"disciplina_{disciplina}_"
                "analise_semanal.csv"
            )

            legenda = (
                f"📊 Análise semanal\n"
                f"Disciplina: {disciplina}\n"
                f"Alunos: {len(tabela)}\n"
                f"Semanas: {len(tabela.columns)}"
            )

            enviar_arquivo_telegram(
                conteudo,
                nome_arquivo,
                legenda,
            )

            sucessos += 1

            print(
                f"Disciplina {disciplina}: OK"
            )

        except Exception as erro:

            falhas += 1

            mensagem = (
                f"❌ ERRO NA DISCIPLINA {disciplina}\n\n"
                f"{erro}"
            )

            print(mensagem)

            try:
                enviar_telegram(mensagem)
            except Exception as erro_telegram:
                print(
                    "Não foi possível enviar o erro "
                    f"ao Telegram: {erro_telegram}"
                )

        # Evita iniciar imediatamente a próxima disciplina.
        time.sleep(DELAY_ENTRE_ACESSOS)

    duracao = time.time() - inicio

    resumo = (
        "\n\n🏁 Crawler semanal finalizado.\n\n"
        f"✅ Sucessos: {sucessos}\n"
        f"❌ Falhas: {falhas}\n"
        f"⏱️ Tempo: {duracao / 60:.1f} minutos"
    )

    enviar_telegram(resumo)

    if falhas:
        raise RuntimeError(
            f"O crawler terminou com {falhas} disciplina(s) "
            "com erro."
        )


if __name__ == "__main__":
    main()
