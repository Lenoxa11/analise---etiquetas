import streamlit as st
import cv2
from pyzbar.pyzbar import decode
import pytesseract
import re
import numpy as np
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Configuração visual da página
st.set_page_config(page_title="Validador de Etiquetas", page_icon="🏷️", layout="centered")

st.title("🏷️ Sistema de Auditoria de Etiquetas")
st.markdown("Desenvolvido para o **Time de Processos** | Validação ágil de layouts e códigos.")

# Função para disparar o e-mail de histórico
def enviar_email_historico(status, nome_arquivo, conteudo_codigo, texto_devolutiva):
    if "email" in st.secrets:
        try:
            remetente = st.secrets["email"]["usuario"]
            senha = st.secrets["email"]["senha"]
            destinatario = st.secrets["email"]["destinatario"]
            smtp_server = st.secrets["email"]["smtp_server"]
            smtp_port = int(st.secrets["email"]["smtp_port"])
            
            msg = MIMEMultipart()
            msg['From'] = remetente
            msg['To'] = destinatario
            msg['Subject'] = f"[{status}] Auditoria de Etiqueta - {nome_arquivo}"
            
            corpo_email = f"""Histórico de Auditoria de Etiqueta
Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
Arquivo: {nome_arquivo}
Status: {status}
Conteúdo do Código Lido: {conteudo_codigo if conteudo_codigo else 'Nenhum'}

--------------------------------------------------
DEVOLUTIVA GERADA:
--------------------------------------------------
{texto_devolutiva}
"""
            msg.attach(MIMEText(corpo_email, 'plain', 'utf-8'))
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(remetente, senha)
            server.sendmail(remetente, destinatario, msg.as_string())
            server.quit()
            return True
        except Exception as e:
            st.error(f"⚠️ Erro técnico ao enviar e-mail de histórico: {e}")
            return False
    return False

# 1. Painel de Entrada de Dados
st.subheader("1. Upload e Particularidades")
arquivo_etiqueta = st.file_uploader("Arraste ou selecione a imagem da etiqueta (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])

observacao_manual = st.text_area("Particularidade ou Observação Manual (Opcional):", 
                                  placeholder="Ex: Nota Fiscal consta no layout, mas divergiu do XML físico recebido.")

if arquivo_etiqueta is not None:
    file_bytes = np.asarray(bytearray(arquivo_etiqueta.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    st.image(img, caption="Etiqueta Enviada", use_container_width=True)
    
    with st.spinner("Auditando etiqueta..."):
        texto_codigo = ""
        tipo_codigo_detectado = "Nenhum"
        
        # 1. TENTA LER CÓDIGO DE BARRAS TRADICIONAL
        codigos_barras = decode(img)
        if codigos_barras:
            texto_codigo = codigos_barras[0].data.decode('utf-8').upper()
            tipo_codigo_detectado = "Código de Barras"
            
        # 2. TENTA LER DATA MATRIX USANDO O OPENCV NATIVO (Sem dependências externas)
        else:
            try:
                detector_dmtx = cv2.DataMatrixDetector()
                resultado_dmtx, _ = detector_dmtx.detectAndDecode(img)
                if resultado_dmtx:
                    if isinstance(resultado_dmtx, (list, tuple)):
                        texto_codigo = resultado_dmtx[0].upper()
                    else:
                        texto_codigo = resultado_dmtx.upper()
                    tipo_codigo_detectado = "Data Matrix"
            except Exception:
                pass
        
        # 3. LEITURA DO LAYOUT (OCR)
        img_cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        texto_layout = pytesseract.image_to_string(img_cinza, lang='por').upper()
        
        st.subheader("2. Resultado da Auditoria")
        
        erros = []
        modo_analise = ""
        
        if texto_codigo:
            modo_analise = f"{tipo_codigo_detectado} + Layout"
            st.info(f"**Modo de Análise:** {modo_analise} | **Conteúdo do Código:** {texto_codigo}")
            
            if texto_codigo.isdigit() and len(texto_codigo) >= 8:
                id_extraido = texto_codigo[:-4]
                vol_extraido_completo = texto_codigo[-4:]
                vol_extraido_limpo = str(int(vol_extraido_completo))
                
                if id_extraido not in texto_layout:
                    erros.append(f"O número identificador '{id_extraido}' do código não foi encontrado impresso no layout.")
                if (vol_extraido_completo not in texto_layout) and (vol_extraido_limpo not in texto_layout):
                    erros.append(f"Contador de volumes '{vol_extraido_completo}' do código não encontrado impresso no layout.")
            else:
                tem_identificador = any(termo in texto_codigo for termo in ["NF", "PEDIDO", "REM", "REMANEJO", "NFE"]) or len(re.findall(r'\d{4,}', texto_codigo)) > 0
                tem_volume = any(termo in texto_codigo for termo in ["/", "VOL", "VLM"])
                
                if not tem_identificador:
                    erros.append(f"Falta identificador obrigatório (NF, Pedido ou Remessa) no {tipo_codigo_detectado}.")
                if not tem_volume:
                    erros.append(f"Contador de volumes não identificado no {tipo_codigo_detectado}.")
                    
        else:
            modo_analise = "Apenas Layout (Etiqueta do cliente não possui código de barras ou Data Matrix)"
            st.warning(f"**Modo de Análise:** {modo_analise}")
            
            tem_identificador_layout = any(termo in texto_layout for termo in ["NF", "NOTA FISCAL", "PEDIDO", "REMESSA", "REM", "NFE"]) or len(re.findall(r'\d{4,}', texto_layout)) > 0
            tem_volume_layout = any(termo in texto_layout for termo in ["/", "VOL", "VOLUME", "VLM", "QTD", "CONTADOR"])
            
            if not tem_identificador_layout:
                erros.append("Não foi encontrado nenhum identificador obrigatório (NF, Nota Fiscal, Pedido ou Remessa) impresso no layout da etiqueta.")
            if not tem_volume_layout:
                erros.append("Não foi encontrado o contador de volumes (ex: VOL, VOLUME ou '/') impresso no layout da etiqueta.")

        if not erros:
            veredit_status = "APROVADA"
            texto_sucesso = f"### 🟢 ETIQUETA HOMOLOGADA!\nTodos os critérios mínimos para o modo [{modo_analise}] foram atendidos com sucesso."
            st.success(texto_sucesso)
            
            texto_final_devolutiva = "Etiqueta aprovada com sucesso pelo Time de Processos."
            if observacao_manual:
                st.warning(f"**Nota de Processos:** {observacao_manual}")
                texto_final_devolutiva += f"\nNota Adicional: {observacao_manual}"
        else:
            veredit_status = "REPROVADA"
            st.error("### 🔴 ETIQUETA REPROVADA")
            st.markdown("Copie o texto abaixo para enviar ao solicitante:")
            
            texto_final_devolutiva = f"""📢 COMUNICADO DE REPROVAÇÃO DE ETIQUETA

Prezado Cliente,

Identificamos que a etiqueta enviada não atende aos requisitos mínimos de homologação e precisará ser ajustada.

• Tipo de Análise realizada: {modo_analise}
• Falhas Identificadas:"""
            
            for erro in erros:
                texto_final_devolutiva += f"\n  - {erro}"

            if observacao_manual:
                texto_devolutiva += f"\n\n• Particularidade identificada pelo auditor: {observacao_manual}"

            texto_final_devolutiva += """

💡 Como corrigir para homologar:
Para que a etiqueta do cliente seja homologada no sistema, a descrição interna do código de barras/Data Matrix (ou o texto impresso do layout, caso não utilize código) deve conter obrigatoriamente pelo menos um desses três dados (NF, Pedido ou Remessa), além do contador de volumes.

Por favor, ajuste a configuração no seu sistema emissor e envie uma nova imagem para validação.

Atenciosamente,
Time de Processos"""
            
            st.text_area("Bloco de Notas (Pronto para envio):", value=texto_final_devolutiva, height=350)
        
        if "email" in st.secrets:
            enviou = enviar_email_historico(veredit_status, arquivo_etiqueta.name, texto_codigo, texto_final_devolutiva)
            if enviou:
                st.caption("📧 Histórico enviado para o seu e-mail com sucesso!")
