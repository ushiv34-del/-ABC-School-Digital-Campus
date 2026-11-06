ABC SCHOOL DIGITAL CAMPUS - ROLL NUMBER ACCESS UPDATE

Use this only in your existing ABC_School_Digital_Campus project folder.
Do not create a new project folder.

1. Stop the running Flask server with Ctrl+C.
2. Extract this ZIP directly into the existing project folder:
   C:\Users\shivu\OneDrive\Documents\ABC_School_Digital_Campus
3. Open CMD in that folder and run:
   .venv\Scripts\python.exe apply_roll_number_update.py
4. Then run:
   .venv\Scripts\python.exe -m py_compile app.py
5. Start the portal:
   .venv\Scripts\python.exe app.py
6. Parents now enter only the student's roll number.

The updater makes backups of the files it replaces. It does not modify:
- instance\abc_school.db
- models.py
- .env
- .venv
- student CSV files

IMPORTANT PRIVACY WARNING:
Roll-number-only access is not authentication. Anyone who knows or guesses a
student's roll number can view that student's result. Do not use this simplified
mode for publicly accessible real student results online. For public launch,
add a simple verified guardian check such as OTP to the registered parent phone.
