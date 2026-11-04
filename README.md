# Android Connect

Gerenciador de arquivos Dual-Pane (Computador e Celular Android) elegante, moderno e sem fio, inspirado na experiência e produtividade do **MT Manager**. Conecte seu dispositivo móvel via Wi-Fi pelo ADB sem cabos, navegue por pastas locais e remotas lado a lado, edite arquivos em tempo real e execute tarefas de administração com segurança e praticidade.

---

## Destaques

- **Conexão Sem Fio Rápida**: Pareamento simples com código de 6 dígitos (`adb pair`) e conexão direta (`adb connect`) com lembrança automática do último IP.
- **Painéis Duplos (Dual-Pane)**: Computador à esquerda e Celular à direita ocupando toda a tela, com suporte a navegação por duplo clique e atalhos rápidos (`/sdcard`, `Home`, `Downloads`, `/tmp`).
- **Edição em Tempo Real com Backup**: Ao dar duplo clique em um arquivo do celular, ele é aberto no programa padrão do seu computador. Ao salvar (`Ctrl+S`), o app detecta a alteração e atualiza o arquivo original no celular, mantendo uma cópia de segurança (`.bak`) isolada.
- **Navegação em `.zip` e `.apk`**: Entre em arquivos comprimidos e pacotes APK como se fossem pastas comuns para inspecionar ou extrair arquivos individuais sem precisar descompactar tudo.
- **Busca Global Recursiva**: Pesquise arquivos e pastas em profundidade em qualquer diretório do computador ou do celular.
- **Renomeador em Lote Inteligente**: Suporte a expressões com tags:
  - `$pacote`: Preserva o nome/pacote base de cada item.
  - `$x`: Sequência numérica automática (1, 2, 3...).
  - `&!`: Ordena a lista em ordem ascendente (A-Z) antes de renomear.
  - `&?`: Ordena a lista em ordem descendente (Z-A) antes de renomear.
  - Execução segura em duas fases para evitar colisões de nomes.
- **Controle de Acesso com Nomes Claros**: Permissões (`chmod`) explicadas em linguagem direta (*Apenas Leitura*, *Leitura e Escrita*, *Padrão do Sistema* e *Acesso Total* condicionado ao modo Root).
- **Modo Acesso Total (Root) Seguro**: Chave de segurança que solicita a senha do computador para liberar pastas do sistema (`/system`, `/data`) e exclusão definitiva da memória. Quando ativado, a interface muda dinamicamente para o tema **Verde Escuro Profundo**.
- **Pré-visualização Universal com Fallback**: Pré-visualizador para imagens e textos/códigos; para formatos binários ou não suportados, oferece botão direto para abrir no aplicativo padrão do notebook.
- **Sincronização com a Fonte do Sistema**: Detecta e aplica automaticamente a mesma família e tamanho de fonte configurados no seu ambiente de trabalho (GNOME, KDE, XFCE).
- **Sem Emojis Bugados**: Interface limpa baseada nos ícones vetoriais oficiais do [Google Material Symbols](https://fonts.google.com/icons).
- **Atalhos de Teclado**:
  - `Tab`: Alterna o foco entre Computador e Celular.
  - `Espaço`: Pré-visualização rápida do arquivo selecionado.
  - `F5`: Copiar para o outro painel.
  - `F6`: Mover para o outro painel.
  - `F7`: Criar nova pasta.
  - `Delete` / `F8`: Apagar itens selecionados.

---

## Instalação

### Opção 1: Via Pacote `.deb` (Recomendado)

Baixe a versão mais recente em [Releases](../../releases) e instale via terminal:

```bash
sudo apt install ./android-connect_2.1.0_all.deb
android-connect
```

O gerenciador de pacotes instalará automaticamente todas as dependências necessárias (`python3`, `python3-pyqt6` ou `python3-pyqt5`, `adb` e `xdg-utils`).

### Opção 2: Executar Diretamente do Código-Fonte

Clone o repositório e execute:

```bash
git clone https://github.com/SEU_USUARIO/android-connect.git
cd android-connect
python3 usr/share/android-connect/main.py
```

---

## Como Compilar o Pacote `.deb`

Para gerar o pacote Debian a partir do código-fonte:

```bash
./build.sh
```

O arquivo `android-connect_2.1.0_all.deb` será gerado na pasta raiz pronto para distribuição.

---

## Estrutura do Projeto

```
android-connect/
├── DEBIAN/
│   ├── control         # Metadados e dependencias do pacote
│   ├── postinst        # Atualizacao do cache de icones e atalhos
│   └── prerm           # Limpeza de caches na desinstalacao
├── usr/
│   ├── bin/
│   │   └── android-connect # Launcher executavel do sistema
│   ├── share/
│   │   ├── android-connect/ # Codigo-fonte da aplicacao
│   │   │   ├── main.py
│   │   │   ├── qt_compat.py
│   │   │   ├── styles.py
│   │   │   ├── adb_backend.py
│   │   │   ├── temp_watcher.py
│   │   │   ├── ui_connect.py
│   │   │   ├── ui_dialogs.py
│   │   │   ├── ui_manager.py
│   │   │   └── icons/       # Icones SVG Google Material Symbols
│   │   ├── applications/
│   │   │   └── android-connect.desktop
│   │   └── icons/hicolor/scalable/apps/
│   │       └── android-connect.svg
├── build.sh            # Script de construcao do pacote .deb
├── .gitignore
└── LICENSE
```

---

## Licença

Distribuído sob a licença MIT. Consulte o arquivo `LICENSE` para mais informações.
