import os
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Cargar variables .env TAMBIÉN en sheets.py
load_dotenv()

SPREADSHEET_ID = os.environ.get("SHEET_ID")

SERVICE_ACCOUNT_FILE = "service_account.json"

def leer_transacciones():
    service = get_sheets_service()

    # Gastos
    r1 = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="Transacciones!B5:E"
    ).execute()

    # Ingresos
    r2 = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="Transacciones!G5:J"
    ).execute()

    gastos = r1.get("values", [])
    ingresos = r2.get("values", [])
    return gastos, ingresos

def get_sheets_service():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)
    return service


def _find_next_row(service, col, start_row):
    # CORRECCIÓN: agregar spreadsheetId obligatorio
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"Transacciones!{col}{start_row}:{col}"
    ).execute()

    values = result.get("values", [])

    # Si no hay datos → usar start_row
    return start_row + len(values)


def add_gasto(fecha, importe, descripcion, categoria):
    service = get_sheets_service()
    next_row = _find_next_row(service, "B", 5)

    body = {
        "values": [[str(fecha), importe, descripcion, categoria]]
    }

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"Transacciones!B{next_row}:E{next_row}",
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


def add_ingreso(fecha, importe, descripcion, categoria):
    service = get_sheets_service()
    next_row = _find_next_row(service, "G", 5)

    body = {
        "values": [[str(fecha), importe, descripcion, categoria]]
    }

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"Transacciones!G{next_row}:J{next_row}",
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()
