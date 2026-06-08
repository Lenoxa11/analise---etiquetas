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

# Função inteligente para desmembrar o conteúdo do código baseado no exemplo do usuário
def quebrar_estrutura_codigo(texto):
    # Se o código usar separadores (como | ou ;), divide por eles
    for sep in ['|', ';', ',']:
        if sep in texto:
            partes = texto.split(sep)
            txt = "**🧩 Campos Divisíveis por Separador:**\n"
            for idx, parte in enumerate(partes):
                txt += f"- Campo {idx+1}: `{parte}`\n"
            return txt, None, None, None, None

    # Se for um bloco numérico longo (Regra de posições fixas pedida pelo usuário)
    if texto.isdigit() and len(texto) >= 12:
        # Lendo da direita para a esquerda:
        vol_total = texto[-3:]          # Últimos 3 dígitos (ex: 002)
        vol_corrente = texto[-6:-3]     # 3 dígitos anteriores (ex: 001)
        nf_extraida = texto[-12:-6]     # 6 dígitos anteriores (ex: 098345)
        cnpj_id = texto[:-12]           # Todo o restante da frente (ex: CNPJ)
        
        txt = f"""**🧩 Estrutura do Código Decodificada:**
* 🏢 **Identificador / CNPJ:** `{cnpj_id}`
* 📄 **Nota Fiscal (NF):** `{nf_extraida}`
* 📊 **Volume Corrente:** `{vol_corrente}`
* 🏁 **Volume Total:** `{vol_total}`"""
        
        return txt, cnpj_id, nf_extraida, vol_corrente, vol_total
        
    return "**🧩 Tipo de Conteúdo:** Texto livre ou formato customizado.", None, None, None, None

# 1. Painel de Entrada de Dados
st.subheader("1. Upload de Arquivo")
arquivo_etiqueta = st.file_uploader("Arraste ou selecione a imagem da etiqueta (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])

observacao_manual = st.text_area("Particularidade ou Observation Manual (Opcional):", 
                                  placeholder="Digite aqui qualquer detalhe extra identificado visualmente.")

if arquivo_etiqueta is not None:
    file_bytes = np.asarray(bytearray(arquivo_etiqueta.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    st.image(img, caption="Etiqueta Enviada", use_container_width=True)
    
    codigos_encontrados = []
    texto_layout = ""
    
    with st.spinner("Analisando layout e rastreando códigos..."):
        img_cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. Rastreia Códigos de Barras e QR Codes
        barcodes_e_qrcodes = decode(img)
        if barcodes_e_qrcodes:
            for obj in barcodes_e_qrcodes:
                codigos_encontrados.append({"tipo": obj.type, "conteudo": obj.data.decode('utf-8').strip().upper()})
        
        # 2. Rastreia Data Matrix com melhoria de imagem
        try:
            detector_dmtx = cv2.DataMatrixDetector()
            resultado_dmtx, _ = detector_dmtx.detectAndDecode(img)
            if not resultado_dmtx:
                resultado_dmtx, _ = detector_dmtx.detectAndDecode(img_cinza)
            if not resultado_dmtx:
                img_maior = cv2.resize(img_cinza, (0, 0), fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                resultado_dmtx, _ = detector_dmtx.detectAndDecode(img_maior)
                
            if resultado_dmtx:
                if isinstance(resultado_dmtx, (list, tuple)):
                    for dmtx in resultado_dmtx:
                        if dmtx: codigos_encontrados.append({"tipo": "DATA MATRIX", "conteudo": dmtx.strip().upper()})
                elif isinstance(resultado_dmtx, str) and resultado_dmtx:
                    codigos_encontrados.append({"tipo": "DATA MATRIX", "conteudo": resultado_dmtx.strip().upper()})
        except Exception:
            pass
        
        # 3. OCR do texto completo
        texto_layout = pytesseract.image_to_string(img_cinza, lang='por').upper()
        
    # --- CAPTURA DE CAMPOS DO LAYOUT IMPRESSO ---
    nf_encontrada = "Não identificada"
    pedido_encontrado = "Não identificado"
    volume_encontrado = "Não identificado"

    nf_busca = re.search(r'(?:NF\s+FISCAL|NOTA\s+FISCAL|NF)[\s\.:]*([0-9\.-]+)', texto_layout)
    if nf_busca: nf_encontrada = nf_busca.group(1).strip()

    pedido_busca = re.search(r'(?:PEDIDO|PED|REMESSA|REM)[\s\.:]*([0-9A-Z\.-]+)', texto_layout)
    if pedido_busca: pedido_encontrado = pedido_busca.group(1).strip()

    vol_busca = re.search(r'(?:VOLUME|VOL)[\s\.:]*([0-9\s\/A-Z-]+)', texto_layout)
    if vol_busca:
        volume_encontrado = vol_busca.group(1).strip()
    else:
        vol_barra = re.search(r'(\d+\s*[\/]\s*\d+)', texto_layout)
        if vol_barra: volume_encontrado = vol_barra.group(1).strip()

    # --- Exibição do Painel de Dados Extraídos ---
    st.subheader("2. Dados Identificados no Layout (Texto)")
    col1, col2, col3 = st.columns(3)
    with col1: st.metric(label="📄 Nota Fiscal (NF)", value=nf_encontrada)
    with col2: st.metric(label="📦 Pedido / Remessa / PED", value=pedido_encontrado)
    with col3: st.metric(label="📊 Volume Mapeado", value=volume_encontrado)

    # --- Relatório de Conformidade Estrutural ---
    st.subheader("3. Relatório de Conformidade")
    erros = []
    texto_desmembramento_completo = ""
    
    if codigos_encontrados:
        modo_analise = "Leitura de Códigos + Layout"
        st.markdown(f"**Método de Verificação:** {modo_analise}")
        
        lista_codigos_str = []
        for c in codigos_encontrados:
            st.markdown(f"### 🔍 Código Detectado (`{c['tipo']}`)")
            st.code(c['conteudo'], language="text")
            lista_codigos_str.append(f"{c['tipo']}({c['conteudo']})")
            
            # CHAMA O DECODIFICADOR PARA DESMEMBRAR O CÓDIGO NA TELA
            explica_layout, c_cnpj, c_nf, c_vol_c, c_vol_t = quebrar_estrutura_codigo(c['conteudo'])
            st.markdown(explica_layout)
            texto_desmembramento_completo += f"\n--- Decomposição do Código [{c['tipo']}]:\n" + explica_layout.replace('*', '') + "\n"
            
            # Validação automatizada contra o texto se o desmembramento funcionar
            if c_nf and nf_encontrada != "Não identificada" and c_nf not in nf_encontrada:
                erros.append(f"A NF `{c_nf}` decodificada no código difere da NF `{nf_encontrada}` impressa no layout.")
            if c_vol_c and volume_encontrado != "Não identificado" and c_vol_c not in volume_encontrado:
                erros.append(f"O volume corrente `{c_vol_c}` decodificado no código difere do volume `{volume_encontrado}` do layout.")
                
        codigos_email_info = " | ".join(lista_codigos_str)
                    
    else:
        modo_analise = "Apenas Layout (Etiqueta sem códigos digitais detectados)"
        st.markdown(f"**Método de Verificação:** {modo_analise}")
        codigos_email_info = "Nenhum"
        
        tem_identificador_layout = any(termo in texto_layout for termo in ["NF", "NOTA FISCAL", "NF FISCAL", "PEDIDO", "PED", "REMESSA", "REM"]) or len(re.findall(r'\d{4,}', texto_layout)) > 0
        tem_volume_layout = any(termo in texto_layout for termo in ["/", "VOL", "VOLUME"])
        
        if not tem_identificador_layout:
            erros.append("Nenhum identificador padrão (NF, Nota Fiscal ou PED) foi localizado no texto impresso.")
        if not tem_volume_layout:
            erros.append("Nenhum indicador de volume (VOL ou VOLUME) foi localizado no texto impresso.")

    # --- Apresentação Final Neutra ---
    st.markdown("---")
    if not erros:
        veredit_status = "CONFORME"
        st.info("ℹ️ **Status:** Estrutura validada sem divergências críticas aparentes.")
        
        texto_final_devolutiva = f"""📢 PARECER TÉCNICO DE LAYOUT - CONFORME

O arquivo enviado foi processado com sucesso.

• NF Identificada: {nf_encontrada}
• Pedido/Remessa/PED: {pedido_encontrado}
• Volume Mapeado: {volume_encontrado}
{texto_desmembramento_completo}
Nenhuma inconformidade estrutural foi identificada."""
        
        if observacao_manual:
            st.markdown(f"**Nota Adicional do Auditor:** {observacao_manual}")
            texto_final_devolutiva += f"\n\n• Observações extras: {observacao_manual}"
            
        st.text_area("Relatório Técnico (Pronto para cópia/envio):", value=texto_final_devolutiva, height=250)
    else:
        veredit_status = "COM APONTAMENTOS"
        st.markdown("### 📋 Parecer Técnico Gerado")
        
        texto_final_devolutiva = f"""📢 PARECER TÉCNICO DE LAYOUT

Abaixo constam os apontamentos gerados pela verificação automática das informações do arquivo enviado:

• Modo de Análise: {modo_analise}
• NF Identificada: {nf_encontrada}
• Pedido/Remessa/PED: {pedido_encontrado}
• Volume Mapeado: {volume_encontrado}
{texto_desmembramento_completo}
• Pontos de Atenção Identificados:"""
        
        for erro in erros:
            texto_final_devolutiva += f"\n  - {erro}"

        if observacao_manual:
            texto_final_devolutiva += f"\n\n• Particularidades observadas pelo auditor: {observacao_manual}"

        texto_final_devolutiva += """

💡 Recomendação de Ajuste:
Alinhar as divergências apontadas acima diretamente nas configurações do sistema emissor para garantir a integridade dos dados impressos."""
        
        st.text_area("Relatório Técnico (Pronto para cópia/envio):", value=texto_final_devolutiva, height=350)
    
    # Dispara o e-mail de histórico
    if "email" in st.secrets:
        enviar_email_historico(veredit_status, arquivo_etiqueta.name, codigos_email_info, texto_final_devolutiva)
