import requests
import subprocess
import getpass
import socket
import platform
import os
import shlex
from typing import Optional, Tuple

MODEL = "meuassistente"
OLLAMA_URL = "http://localhost:11434/api/generate"

SYSTEM_INFO = {
    "user": getpass.getuser(),
    "hostname": socket.gethostname(),
    "distro": platform.platform(),
    "kernel": platform.release(),
}

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf *", ":(){:|:&};:", "mkfs", "dd if=", "dd of=",
    ">/dev/", "> /dev/", "> /etc/", "chmod 777 /", "chown root",
    "reboot", "poweroff", "halt", "shutdown", "init 0",
    "sudo rm", "sudo -s", "sudo su", "sudo bash", "sudo sh",
    "rm -rf ~", "rm -rf $home"
]


def is_dangerous(cmd: str) -> bool:
    c = cmd.lower().strip()
    return any(p in c for p in DANGEROUS_PATTERNS)


def ask_ollama(prompt: str, timeout: int = 60) -> str:
    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1}
            },
            timeout=timeout
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.RequestException as e:
        return f"Erro de conexão: {e}"
    except Exception as e:
        return f"Erro inesperado: {e}"


def parse_response(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Aceita:
    TIPO: COMANDO
    RESPOSTA: ls -la

    OU:

    TIPO: COMANDO
    ls -la
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    tipo = None
    resposta = None

    for i, line in enumerate(lines):
        if line.upper().startswith("TIPO:"):
            tipo = line.split(":", 1)[1].strip().upper()

            # tenta achar RESPOSTA:
            for j in range(i + 1, len(lines)):
                if lines[j].upper().startswith("RESPOSTA:"):
                    resposta = lines[j].split(":", 1)[1].strip()
                    if j + 1 < len(lines):
                        resposta += "\n" + "\n".join(lines[j+1:])
                    return tipo, resposta

            # fallback: próxima linha já é a resposta
            if i + 1 < len(lines):
                resposta = lines[i + 1].strip()

            return tipo, resposta

    return tipo, resposta


def safe_split_command(cmd: str):
    try:
        return shlex.split(cmd)
    except:
        return None


def main():
    memory: list[str] = []

    print("Assistente Linux local ativo")
    print("Digite 'sair' para encerrar")

    while True:
        try:
            user_input = input("\nVocê> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nEncerrando.")
            break

        if not user_input:
            continue

        if user_input.lower() in {"sair", "exit", "quit"}:
            print("Encerrado.")
            break

        memory.append(f"Usuário: {user_input}")
        history = "\n".join(memory[-8:])

        system_context = f"""
Usuário: {SYSTEM_INFO['user']}
Máquina: {SYSTEM_INFO['hostname']}
Sistema: {SYSTEM_INFO['distro']}
Kernel: {SYSTEM_INFO['kernel']}
Diretório atual: {os.getcwd()}
"""

        prompt = f"""
Você é um assistente Linux seguro.

{system_context}

Histórico:
{history}

Responda usando EXATAMENTE um formato:

TIPO: TEXTO
RESPOSTA: texto

TIPO: COMANDO
RESPOSTA: comando

TIPO: NADA
RESPOSTA: motivo curto

Nunca omita "RESPOSTA:".

Pedido: {user_input}
"""

        raw = ask_ollama(prompt)

        if raw.startswith("Erro"):
            print(raw)
            continue

        memory.append(f"IA: {raw}")

        tipo, resposta = parse_response(raw)

        # fallback se o modelo só cuspiu um comando seco
        if not tipo and raw and "\n" not in raw:
            tipo = "COMANDO"
            resposta = raw.strip()

        if tipo == "COMANDO" and resposta:
            cmd = resposta.strip()

            if is_dangerous(cmd):
                print("Comando bloqueado por segurança:")
                print(cmd)
                continue

            args = safe_split_command(cmd)
            if not args:
                print("Falha ao interpretar o comando.")
                continue

            print("\nComando sugerido:")
            print(" ", cmd)

            if input("Executar? [s/N]: ").lower() != "s":
                print("Cancelado.")
                continue

            print("\nExecutando...\n" + "=" * 50)

            try:
                result = subprocess.run(
                    args,
                    text=True,
                    capture_output=True,
                    env=os.environ.copy()
                )

                if result.stdout:
                    print(result.stdout.rstrip())

                if result.stderr:
                    print("\nErro:")
                    print(result.stderr.rstrip())

                if result.returncode != 0:
                    print(f"\nCódigo de saída: {result.returncode}")

            except FileNotFoundError:
                print(f"Comando não encontrado: {args[0]}")
            except Exception as e:
                print(f"Erro ao executar: {e}")

            print("=" * 50)

        elif tipo in ("TEXTO", "NADA") and resposta:
            print(resposta)

        else:
            print("Resposta fora do padrão:")
            print(raw)


if __name__ == "__main__":
    main()
