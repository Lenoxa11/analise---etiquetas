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
def enviar_email_historico(status, nome_arquivo, codigos_listados, texto_devolutiva):
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
Códigos Lidos: {codigos_listados if codigos_listados else 'Nenhum'}

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
    
    codigos_encontrados = []
    texto_layout = ""
    
    with st.spinner("Analisando layout e rastreando códigos..."):
        # AJUSTE 1: LEITURA MULTI-CÓDIGOS (Barras, QR Codes e Data Matrix juntos)
        # 1. Localiza Códigos de Barras e QR Codes tradicionais
        barcodes_e_qrcodes = decode(img)
        if barcodes_e_qrcodes:
            for obj in barcodes_e_qrcodes:
                conteudo = obj.data.decode('utf-8').strip().upper()
                tipo = obj.type
                codigos_encontrados.append({"tipo": tipo, "conteudo": conteudo})
        
        # 2. Localiza códigos Data Matrix nativos do OpenCV
        try:
            detector_dmtx = cv2.DataMatrixDetector()
            resultado_dmtx, _ = detector_dmtx.detectAndDecode(img)
            if resultado_dmtx:
                if isinstance(resultado_dmtx, (list, tuple)):
                    for dmtx in resultado_dmtx:
                        if dmtx:
                            codigos_encontrados.append({"tipo": "DATA MATRIX", "conteudo": dmtx.strip().upper()})
                elif isinstance(resultado_dmtx, str) and resultado_dmtx:
                    codigos_encontrados.append({"tipo": "DATA MATRIX", "conteudo": resultado_dmtx.strip().upper()})
        except Exception:
            pass
        
        # 3. Leitura textual do layout (OCR)
        img_cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        texto_layout = pytesseract.image_to_string(img_cinza, lang='por').upper()
        
    # --- AJUSTES 2, 3 e 4: BUSCA FLEXÍVEL DE IDENTIFICADORES (Maiúsculo/Minúsculo) ---
    nf_encontrada = "Não identificada"
    pedido_encontrado = "Não identificado"
    volume_encontrado = "Não identificado"

    # Reconhece: NOTA FISCAL, NF, NF FISCAL (e variações com pontos, espaços ou dois pontos)
    nf_busca = re.search(r'(?:NF\s+FISCAL|NOTA\s+FISCAL|NF)[\s\.:]*([0-9\.-]+)', texto_layout)
    if nf_busca:
        nf_encontrada = nf_busca.group(1).strip()
    else:
        numeros_longos = re.findall(r'\b\d{5,9}\b', texto_layout)
        if numeros_longos:
            nf_encontrada = numeros_longos[0]

    # Reconhece: PEDIDO, PED, REMESSA, REM
    pedido_busca = re.search(r'(?:PEDIDO|PED|REMESSA|REM)[\s\.:]*([0-9A-Z\.-]+)', texto_layout)
    if pedido_busca:
        pedido_encontrado = pedido_busca.group(1).strip()

    # Reconhece: VOLUME, VOL (captura correntes e totais como "1/2", "1 DE 2")
    vol_busca = re.search(r'(?:VOLUME|VOL)[\s\.:]*([0-9\s\/A-Z-]+)', texto_layout)
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
        st.metric(label="📊 Volume Mapeado", value=volume_encontrado)

    # --- Relatório de Conformidade Estrutural ---
    st.subheader("3. Relatório de Conformidade")
    erros = []
    
    # Processamento caso existam códigos detectados
    if codigos_encontrados:
        modo_analise = "Leitura de Códigos + Layout"
        st.markdown(f"**Método de Verificação:** {modo_analise}")
        
        # Mostra todos os códigos achados na tela de forma organizada
        st.markdown("**Códigos Estruturais Encontrados:**")
        lista_codigos_str = []
        for c in codigos_encontrados:
            st.caption(f"🔹 **Tipo:** `{c['tipo']}` | **Conteúdo:** `{c['conteudo']}`")
            lista_codigos_str.append(f"{c['tipo']}({c['conteudo']})")
        codigos_email_info = " | ".join(lista_codigos_str)
        
        # Validação estrutural de cada código contra o texto impresso
        for c in codigos_encontrados:
            texto_codigo = c['conteudo']
            if texto_codigo.isdigit() and len(texto_codigo) >= 8:
                id_extraido = texto_codigo[:-4]
                vol_extraido_completo = texto_codigo[-4:]
                vol_extraido_limpo = str(int(vol_extraido_completo))
                
                if id_extraido not in texto_layout:
                    erros.append(f"O identificador '{id_extraido}' contido no código `{c['tipo']}` não foi achado no texto impresso.")
                if (vol_extraido_completo not in texto_layout) and (vol_extraido_limpo not in texto_layout):
                    erros.append(f"O volume '{vol_extraido_completo}' contido no código `{c['tipo']}` não foi achado no texto impresso.")
            else:
                tem_identificador = any(termo in texto_codigo for termo in ["NF", "PEDIDO", "PED", "REM", "NFE"]) or len(re.findall(r'\d{4,}', texto_codigo)) > 0
                tem_volume = any(termo in texto_codigo for termo in ["/", "VOL", "VOLUME"])
                
                if not tem_identificador:
                    erros.append(f"Falta identificador de origem (NF, PED ou REM) dentro do código `{c['tipo']}`.")
                if not tem_volume:
                    erros.append(f"Contador de volumes não mapeado no conteúdo do código `{c['tipo']}`.")
                if texto_codigo not in texto_layout and nf_encontrada not in texto_codigo and pedido_encontrado not in texto_codigo:
                    erros.append(f"Os dados do código `{c['tipo']}` parecem divergir do texto do layout.")
                    
    else:
        modo_analise = "Apenas Layout (Etiqueta sem códigos digitais detectados)"
        st.markdown(f"**Método de Verificação:** {modo_analise}")
        codigos_email_info = "Nenhum"
        
        tem_identificador_layout = any(termo in texto_layout for termo in ["NF", "NOTA FISCAL", "NF FISCAL", "PEDIDO", "PED", "REMESSA", "REM"]) or len(re.findall(r'\d{4,}', texto_layout)) > 0
        tem_volume_layout = any(termo in texto_layout for termo in ["/", "VOL", "VOLUME"])
        
        if not tem_identificador_layout:
            erros.append("Nenhum identificador padrão (NF, Nota Fiscal, Pedido ou PED) foi localizado no texto impresso.")
        if not tem_volume_layout:
            erros.append("Nenhum indicador de volume (VOL ou VOLUME) foi localizado no texto impresso.")

    # --- Apresentação Final Neutra ---
    if not erros:
        veredit_status = "CONFORME"
        st.info("ℹ️ **Status:** Nenhuma inconsistência estrutural foi encontrada entre os códigos e o texto do layout.")
        
        texto_final_devolutiva = f"""📢 PARECER TÉCNICO DE LAYOUT - CONFORME

O arquivo enviado foi processado com sucesso.

• NF Identificada: {nf_encontrada}
• Pedido/Remessa/PED: {pedido_encontrado}
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
• Pedido/Remessa/PED: {pedido_encontrado}
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
    
    # Dispara o e-mail de histórico atualizado
    if "email" in st.secrets:
        enviar_email_historico(veredit_status, arquivo_etiqueta.name, codigos_email_info, texto_final_devolutiva)
