@echo off
echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate
echo Installing dependencies...
pip install PyQt6 PyOpenGL PyOpenGL_accelerate numpy trimesh shapely scipy networkx
echo.
echo Setup complete! Run run.bat to start the application.
pause
