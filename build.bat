@echo off
echo Building 3D Slicer Pro...
pip install pyinstaller --quiet
pyinstaller slicer3d.spec --clean
echo.
echo Done! Executable is at: dist\3DSlicerPro\3DSlicerPro.exe
pause
