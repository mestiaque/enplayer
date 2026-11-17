/* ENPlayer.exe: starts ENPlayer with the bundled Python.
 *
 * Windows names a program after its .exe (version info + icon) in "Open with", the taskbar,
 * Task Manager and Default apps. ENPlayer used to run as bin\pythonw.exe, so Windows showed
 * it as "Python" there instead of ENPlayer. This launcher embeds the same bundled Python
 * (it sits next to libpython3.x.dll in bin\, so Python finds its lib\ folder exactly like
 * pythonw.exe does) and runs `-m neplayer.main <files…>` inside its own process.
 *
 * Built by build-windows.sh:  gcc -municode -mwindows launcher.c launcher.res -lpython3.x
 */
#include <Python.h>
#include <windows.h>
#include <shellapi.h>
#include <stdlib.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR cmdline, int show)
{
    (void)instance; (void)previous; (void)cmdline; (void)show;
    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv || argc < 1)
        return 1;
    wchar_t **args = calloc((size_t)argc + 3, sizeof *args);
    if (!args)
        return 1;
    int n = 0;
    args[n++] = argv[0];
    args[n++] = L"-m";
    args[n++] = L"neplayer.main";
    for (int i = 1; i < argc; i++)
        args[n++] = argv[i];
    args[n] = NULL;
    return Py_Main(n, args);
}
