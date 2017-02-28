from setuptools import setup


install_requires = (
    "cmdtree",
    "requests",
    "tqdm",
)

setup(
    name='huaban-exporter',
    version='0.0.3',
    py_modules=["huaban_exporter"],
    install_requires=install_requires,
    url='https://github.com/winkidney/huaban-exporter',
    license='MIT',
    author='winkidney',
    author_email='winkidney@gmail.com',
    description='Backup tool for huaban user.'
                'Save pictures from huaban.',
    entry_points={
        'console_scripts': ['huaban=huaban_exporter:cmd.entry'],
    }
)
