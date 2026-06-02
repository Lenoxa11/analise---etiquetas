import streamlit as st
import cv2
from pyzbar.pyzbar import decode
import pytesseract
import re
import numpy as np

# Configuração visual da página
st.set_page_config(page_title="Validador de Etiquetas", page_icon="🏷️", layout="centered")

st.title("🏷️ Sistema de Auditoria de Etiquetas")
st.markdown("Desenvolvido para o **Time de Processos** | Validação ágil de layouts e códigos de barras.")

# 1. Painel de Entrada de Dados
st.subheader("1. Upload e Particularidades")
arquivo_etiqueta = st.file_uploader("Arraste ou selecione a imagem da etiqueta (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])

# Campo para o operador adicionar observações manuais caso a etiqueta tenha alguma particularidade
observacao_manual = st.text_area("Particularidade ou Observação Manual (Opcional):", 
                                  placeholder="Ex: Nota Fiscal consta no layout, mas divergiu do XML físico recebido.")

if arquivo_etiqueta is not None:
    # Processamento da Imagem
    file_bytes = np.asarray(bytearray(arquivo_etiqueta.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    
    st.image(img, caption="Etiqueta Enviada", use_container_width=True)
    
    with st.spinner("Auditando etiqueta..."):
        # Leitura do Código de Barras
        codigos = decode(img)
        texto_codigo = codigos[0].data.decode('utf-8').upper() if codigos else ""
        
        # Leitura do Layout (OCR)
        img_cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        texto_layout = pytesseract.image_to_string(img_cinza, lang='por').upper()
        
        # Motor de Regras (Busca por NF, Pedido ou Remessa)
        tem_identificador = any(termo in texto_codigo for termo in ["NF", "PEDIDO", "REM", "REMANEJO", "NFE"]) or len(re.findall(r'\d{4,}', texto_codigo)) > 0
        
        st.subheader("2. Resultado da Auditoria")
        st.info(f"**Conteúdo lido no Código de Barras:** {texto_codigo if texto_codigo else 'Nenhum código detectado'}")
        
        if tem_identificador:
            st.success("### 🟢 ETIQUETA HOMOLOGADA!\nOs dados essenciais foram encontrados no código de barras.")
            if observacao_manual:
                st.warning(f"**Nota de Processos:** {observacao_manual}")
        else:
            st.error("### 🔴 ETIQUETA REPROVADA")
            st.markdown("Copie o texto abaixo para enviar ao solicitante:")
            
            # Montagem do Bloco de Notas Automático + Manual
            texto_devolutiva = f"""📢 COMUNICADO DE REPROVAÇÃO DE ETIQUETA

Prezado Cliente,

Identificamos que a etiqueta enviada não atende aos requisitos mínimos de homologação e precisará ser ajustada.

• O que foi identificado: O código de barras lido pelo sistema não contém as informações obrigatórias vinculadas (Número da Nota Fiscal, Pedido ou Remessa).
• Conteúdo atual do seu código: {texto_codigo if texto_codigo else 'Código ilegível ou ausente'}"""

            # Injeta a observação manual se o usuário tiver digitado alguma
            if observacao_manual:
                texto_devolutiva += f"\n\n• Particularidade identificada pelo auditor: {observacao_manual}"

            texto_devolutiva += """

💡 Como corrigir para homologar:
Para que a etiqueta do cliente seja homologada no sistema, a descrição interna do código de barras deve conter obrigatoriamente pelo menos um desses três dados (NF, Pedido ou Remessa), além do contador de volumes.

Por favor, ajuste a configuração no seu sistema emissor e envie uma nova imagem para validação.

Atenciosamente,
Time de Processos"""
            
            # Caixa de texto com botão de "Clique para copiar" nativo do Streamlit
            st.text_area("Bloco de Notas (Pronto para envio):", value=texto_devolutiva, height=350)
