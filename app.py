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
st.markdown("Desenvolvido para o **Time de Processos** | Análise e leitura de layouts.")

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
            msg['Subject'] = f"[{status}] Análise de Etiqueta - {nome_arquivo}"
            
            corpo_email = f"""Histórico de Auditoria de Etiqueta
Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
Arquivo: {nome_arquivo}
Status: {status}
Conteúdo do Código Lido: {conteudo_codigo if conteudo_codigo else 'Nenhum'}

--------------------------------------------------
PARECER GERADO:
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
        except Exception:
            return False
    return False

# 1. Painel de Entrada de Dados
st.subheader("1. Upload de Arquivo")
arquivo_etiqueta = st.file_uploader("Arraste ou selecione a imagem da etiqueta (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])

observacao_manual = st.text_area("Particularidade ou Observação Manual (Opcional):", 
                                  placeholder="Digite aqui qualquer detalhe extra identificado visualmente.")

if arquivo_etiqueta is not None:
    file_bytes = np.asarray(bytearray(arquivo_etiqueta.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    st.image(img, caption="Etiqueta Enviada", use_container_width=True)
    
    texto_codigo = ""
    tipo_codigo_detectado = "Nenhum"
    texto_layout = ""
    
    # Processamento pesado em segundo plano (OCR e Códigos)
    with st.spinner("Analisando layout da etiqueta..."):
        # 1. Tenta ler código de barras tradicional
        codigos_barras = decode(img)
        if codigos_barras:
            texto_codigo = codigos_barras[0].data.decode('utf-8').upper()
            tipo_codigo_detectado = "Código de Barras"
        # 2. Tenta ler Data Matrix nativo
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
        
        # 3. Leitura do layout (OCR)
        img_cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        texto_layout = pytesseract.image_to_string(img_cinza, lang='por').upper()
        
    # --- MOTOR DE EXTRAÇÃO DE DADOS (NOVA FUNÇÃO) ---
    nf_encontrada = "Não identificada"
    pedido_encontrado = "Não identificado"
    volume_encontrado = "Não identificado"

    # Captura padrões de NF (ex: NF: 123456 ou NFE 1234)
    nf_busca = re.search(r'(?:NF|NOTA\s+FISCAL|NFE)[\s\.:]*([0-9\.-]+)', texto_layout)
    if nf_busca:
        nf_encontrada = nf_busca.group(1).strip()
    else:
        # Se não achar a palavra NF, busca um bloco numérico longo comum de NF (5 a 9 dígitos)
        numeros_longos = re.findall(r'\b\d{5,9}\b', texto_layout)
        if numeros_longos:
            nf_encontrada = numeros_longos[0]

    # Captura padrões de Pedido ou Remessa
    pedido_busca = re.search(r'(?:PEDIDO|REMESSA|REM|PED)[\s\.:]*([0-9A-Z\.-]+)', texto_layout)
    if pedido_busca:
        pedido_encontrado = pedido_busca.group(1).strip()

    # Captura padrões de Volume (ex: VOL: 1/2 ou 001/002)
    vol_busca = re.search(r'(?:VOL|VOLUME|VLM)[\s\.:]*([0-9\s\/]+)', texto_layout)
    if vol_busca:
        volume_encontrado = vol_busca.group(1).strip()
    else:
        vol_barra = re.search(r'(\d+\s*[\/]\s*\d+)', texto_layout)
        if vol_barra:
            volume_encontrado = vol_barra.group(1).strip()

    # --- Exibição do Painel de Dados Extraídos ---
    st.subheader("2. Dados Identificados no Layout (Texto)")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="📄 Nota Fiscal (NF)", value=nf_encontrada)
    with col2:
        st.metric(label="📦 Pedido / Remessa", value=pedido_encontrado)
    with col3:
        st.metric(label="📊 Volume", value=volume_encontrado)

    # --- Relatório de Conformidade Estrutural ---
    st.subheader("3. Relatório de Conformidade")
    erros = []
    
    if texto_codigo:
        modo_analise = f"{tipo_codigo_detectado} + Layout"
        st.markdown(f"**Método de Verificação:** {modo_analise}  \n**Conteúdo Estrutural do Código:** `{texto_codigo}`")
        
        if texto_codigo.isdigit() and len(texto_codigo) >= 8:
            id_extraido = texto_codigo[:-4]
            vol_extraido_completo = texto_codigo[-4:]
            vol_extraido_limpo = str(int(vol_extraido_completo))
            
            if id_extraido not in texto_layout:
                erros.append(f"O número identificador '{id_extraido}' do código não consta no texto impresso.")
            if (vol_extraido_completo not in texto_layout) and (vol_extraido_limpo not in texto_layout):
                erros.append(f"O contador de volumes '{vol_extraido_completo}' do código não consta no texto impresso.")
        else:
            tem_identificador = any(termo in texto_codigo for termo in ["NF", "PEDIDO", "REM", "REMANEJO", "NFE"]) or len(re.findall(r'\d{4,}', texto_codigo)) > 0
            tem_volume = any(termo in texto_codigo for termo in ["/", "VOL", "VLM"])
            
            if not tem_identificador:
                erros.append(f"Falta identificador (NF, Pedido ou Remessa) nas informações internas do {tipo_codigo_detectado}.")
            if not tem_volume:
                erros.append(f"Contador de volumes não mapeado dentro do {tipo_codigo_detectado}.")
                
    else:
        modo_analise = "Apenas Layout (Etiqueta sem código de barras/Data Matrix detectado)"
        st.markdown(f"**Método de Verificação:** {modo_analise}")
        
        tem_identificador_layout = any(termo in texto_layout for termo in ["NF", "NOTA FISCAL", "PEDIDO", "REMESSA", "REM", "NFE"]) or len(re.findall(r'\d{4,}', texto_layout)) > 0
        tem_volume_layout = any(termo in texto_layout for termo in ["/", "VOL", "VOLUME", "VLM", "QTD", "CONTADOR"])
        
        if not tem_identificador_layout:
            erros.append("Não foi encontrado nenhum identificador padrão (NF, Nota Fiscal, Pedido ou Remessa) impresso no layout.")
        if not tem_volume_layout:
            erros.append("Não foi encontrado o indicador de volume (ex: VOL, VOLUME ou '/') impresso no layout.")

    # Apresentação Final Neutra
    if not erros:
        veredit_status = "CONFORME"
        st.info("ℹ️ **Status:** Nenhuma inconsistência estrutural foi encontrada entre os códigos e o texto do layout.")
        
        texto_final_devolutiva = f"""📢 PARECER TÉCNICO DE LAYOUT - CONFORME

O arquivo enviado foi processado com sucesso.

• NF Identificada: {nf_encontrada}
• Pedido/Remessa: {pedido_encontrado}
• Volume Mapeado: {volume_encontrado}

Nenhuma inconformidade estrutural foi identificada."""
        
        if observacao_manual:
            st.markdown(f"**Nota Adicional do Auditor:** {observacao_manual}")
            texto_final_devolutiva += f"\n\n• Observações extras: {observacao_manual}"
            
        st.text_area("Relatório Técnico (Pronto para cópia/envio):", value=texto_final_devolutiva, height=200)
    else:
        veredit_status = "COM APONTAMENTOS"
        st.markdown("### 📋 Parecer Técnico Gerado")
        
        texto_final_devolutiva = f"""📢 PARECER TÉCNICO DE LAYOUT

Abaixo constam os apontamentos gerados pela verificação automática das informações do arquivo enviado:

• Modo de Análise: {modo_analise}
• NF Identificada: {nf_encontrada}
• Pedido/Remessa: {pedido_encontrado}
• Volume Mapeado: {volume_encontrado}

• Pontos de Atenção Identificados:"""
        
        for erro in erros:
            texto_final_devolutiva += f"\n  - {erro}"

        if observacao_manual:
            texto_final_devolutiva += f"\n\n• Particularidades observadas pelo auditor: {observacao_manual}"

        texto_final_devolutiva += """

💡 Recomendação de Ajuste:
Alinhar as divergências apontadas acima diretamente nas configurações do sistema emissor para garantir a integridade dos dados impressos."""
        
        st.text_area("Relatório Técnico (Pronto para cópia/envio):", value=texto_final_devolutiva, height=320)
    
    # Dispara o e-mail de histórico
    if "email" in st.secrets:
        enviar_email_historico(veredit_status, arquivo_etiqueta.name, texto_codigo, texto_final_devolutiva)
