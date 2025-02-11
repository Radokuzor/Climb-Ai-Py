from google.cloud import firestore

db = firestore.Client.from_service_account_json('./climb-ai-firebase-adminsdk-fbsvc-f3d3bbdabd.json')
