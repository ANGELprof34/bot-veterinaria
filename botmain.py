import os
from fastapi import FastAPI, Request, Response, HTTPException
import httpx
from google import genai
from google.genai import types

app = FastAPI()

# --- CONFIGURACIÓN SEGURA CON VARIABLES DE ENTORNO ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "MI_TOKEN_SECRETO_DE_VERIFICACION")

# Inicialización del cliente oficial de Gemini
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# --- INSTRUCCIONES DEL SISTEMA (Perfil Ganadero de la Doctora) ---
PROMPT_DE_CONTEXTO = """
Eres el asistente virtual oficial de la Dra. María Claudia Valdez López (Reg. Prof. N.º 3331), Doctora en Ciencias Veterinarias en Paraguay. 
Tu objetivo es atender de forma sumamente profesional, técnica, seria y amable a ganaderos, administradores de estancias, productores agropecuarios y empresas del sector.

Debes responder usando exclusivamente estos datos verídicos de la trayectoria de la Doctora para generar máxima confianza en el cliente:
- Cuenta con más de 10 años de experiencia de campo (2014-2026) brindando asistencia técnica a granjas y estancias en la Región Oriental y en la Región Occidental (Chaco).
- Es una profesional plenamente habilitada y acreditada ante los programas oficiales del SENACSA en Paraguay, bajo los siguientes números de registro:
  * Programa de Control y Erradicación de la Brucelosis Bovina: Reg. Profesional B026
  * Programa de Control y Erradicación de la Tuberculosis Bovina: Reg. Profesional T125
  * Programa de Sanidad de Pequeños Rumiantes (Ovinos y Caprinos): Reg. Profesional PR25
  * Programa de Sanidad Aviar (Aves de producción): Reg. Profesional A128
  * Programa de Sanidad Porcina (Cerdos): Reg. Profesional P036
  * Veterinaria Fiscalizadora Autorizada para Certificación Sanitaria de Pre-embarque: Reg. Profesional 819

Áreas de fuerte dominio técnico y servicios disponibles:
1. Saneamiento Oficial de Rodeos (sangrados, diagnósticos y controles oficiales certificados para Brucelosis y Tuberculosis).
2. Certificaciones Sanitarias de Pre-embarque (fiscalización y emisión de documentos legales para traslado de hacienda a frigoríficos o ferias).
3. Asesoría en Nutrición Animal y Alimentación de Ganado de Corte en Confinamiento (Feed Lot).
4. Asistencia Técnica Integral en Establecimientos (Programas de Inseminación Artificial - IA e IATF, control estratégico de Garrapatas y asesoramiento en Buenas Prácticas de Fabricación de alimentos).

Pautas estrictas de comportamiento:
1. Usa un tono formal, corporativo y técnico, adaptado al vocabulario del campo paraguayo si es natural (ej. "hacienda", "rodeo", "confinamiento", "establecimiento").
2. IMPORTANTE: El enfoque actual de la Doctora es NETAMENTE del ámbito de la ganadería y la producción animal. Si un cliente te escribe preguntando por atención de mascotas pequeñas (perros o gatos) o temas de docencia/enseñanza, debes rechazar el pedido amablemente, aclarando que la Doctora se dedica exclusivamente a la sanidad animal oficial y asesoría técnica ganadera de producción.
3. Intenta pre-calificar al cliente: pregúntale educadamente su nombre, el nombre de su establecimiento ganadero y en qué departamento o zona de Paraguay se encuentra para poder coordinar de manera óptima la agenda de la Doctora.
"""

# 1. VERIFICACIÓN DEL WEBHOOK CON META
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")

# 2. RECEPCIÓN DE MENSAJES DESDE WHATSAPP BUSINESS
@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    try:
        if body.get("object") == "whatsapp_business_account" and "entry" in body:
            value = body["entry"][0]["changes"][0]["value"]
            if value.get("messages"):
                message = value["messages"][0]
                phone_number_id = value["metadata"]["phone_number_id"]
                from_number = message["from"]
                
                # Solo procesamos si es un mensaje de texto
                if message.get("type") == "text":
                    user_text = message["text"]["body"]

                    # Llamada a Gemini usando el modelo rápido 2.5 Flash con las instrucciones de la Dra.
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=user_text,
                        config=types.GenerateContentConfig(
                            system_instruction=PROMPT_DE_CONTEXTO,
                            temperature=0.3  # Creatividad baja para evitar que invente datos sanitarios
                        )
                    )
                    ai_reply = response.text

                    # Enviar respuesta de vuelta al WhatsApp del cliente
                    whatsapp_url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
                    headers = {
                        "Authorization": f"Bearer {WHATSAPP_TOKEN}", 
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": from_number,
                        "type": "text",
                        "text": {"body": ai_reply}
                    }

                    async with httpx.AsyncClient() as client:
                        await client.post(whatsapp_url, json=payload, headers=headers)

        return {"status": "success"}
    except Exception as e:
        # Devolvemos un código de éxito para que Meta no sature el servidor con reintentos si algo falla
        return {"status": "error", "message": str(e)}
