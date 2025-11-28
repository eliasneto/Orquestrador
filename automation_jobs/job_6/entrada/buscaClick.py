from pynput.mouse import Listener
import ctypes
import time

# Função para obter a posição da janela do Chrome
def get_chrome_window_position():
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()  # Pega a janela ativa (garante que o Chrome esteja em primeiro plano)
    
    if hwnd == 0:
        print("Erro: Não foi possível obter a janela ativa.")
        return None

    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom

# Função para pegar o DPI do monitor da janela ativa
def get_dpi(hwnd):
    try:
        # Usar o método GetDpiForWindow da shcore para capturar o DPI da janela ativa
        shcore = ctypes.windll.shcore
        dpi = ctypes.c_uint()
        shcore.GetDpiForWindow(hwnd, ctypes.byref(dpi))
        
        # Retorna a escala (DPI normalizado)
        scale = dpi.value / 96.0  # Normaliza para a escala do sistema (DPI padrão = 96)
        if scale == 0:  # Se o DPI for zero, retornamos 1.0 para evitar divisão por zero
            print("DPI retornado foi zero, usando escala padrão 1.0")
            scale = 1.0
        return scale
    except Exception as e:
        print(f"Erro ao pegar DPI: {e}")
        return 1.0  # Retorna 1.0 caso falhe ao pegar o DPI

# Lista para armazenar as coordenadas de cada clique
clics = []

# Função que será chamada quando o mouse for clicado
def on_click(x, y, button, pressed):
    if pressed:  # Verifica se o clique é de "pressionar"
        # Obter a posição da janela do Chrome
        window_position = get_chrome_window_position()
        
        if window_position is None:
            return
        
        L, T, R, B = window_position
        # Obter o DPI da janela ativa
        scale = get_dpi(ctypes.windll.user32.GetForegroundWindow())
        
        # Calcular as coordenadas relativas ao Chrome
        relative_x = (x - L) / scale  # Dividindo pela escala (fator de DPI)
        relative_y = (y - T) / scale  # Dividindo pela escala (fator de DPI)
        
        clics.append((relative_x, relative_y))  # Armazena as coordenadas relativas
        print(f"Você clicou nas coordenadas relativas X={relative_x} Y={relative_y} (com DPI: {scale})")

# Iniciar o Listener para escutar os cliques do mouse
with Listener(on_click=on_click) as listener:
    listener.join()

# Exibir todas as coordenadas capturadas após o término do Listener
print("\nCoordenadas capturadas (relativas à janela do Chrome):")
for index, (x, y) in enumerate(clics, 1):
    print(f"Clique {index}: X={x}, Y={y}")
