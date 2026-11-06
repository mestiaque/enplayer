from setuptools import find_packages, setup

setup(
    name='neplayer',
    version='1.4.1',
    description='Native GTK4 video library and player with live hover previews',
    packages=find_packages(exclude=['tests']),
    package_data={'neplayer': ['resources/styles/*.css', 'resources/styles/themes/*.css', 'resources/icons/NEPLAYER/index.theme', 'visualizer/*.glsl', 'visualizer/presets/*.glsl', 'resources/icons/NEPLAYER/*.txt', 'resources/icons/NEPLAYER/scalable/actions/*.svg', 'resources/icons/*.svg', 'resources/icons/*.png']},
    include_package_data=True,
    python_requires='>=3.10',
    install_requires=['PyGObject>=3.42', 'python-mpv>=1.0.4', 'Pillow>=9.0'],
    entry_points={'gui_scripts': ['enplayer=neplayer.main:main']},
)
