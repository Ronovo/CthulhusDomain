import pygame
import json
import os
import random
from typing import Optional, Dict, Any
import sys

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
FPS = 60

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
DARK_GREEN = (0, 100, 0)
PURPLE = (128, 0, 128)
DARK_GREY = (30, 30, 30)  # New dark grey background color

# Get the base directory for the game
if getattr(sys, 'frozen', False):
    # If we're running as a bundled executable
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # If we're running as a script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure required directories exist
os.makedirs(os.path.join(BASE_DIR, "Games"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "fonts"), exist_ok=True)

# Great Old One Names
GREAT_OLD_ONES = [
    "Cthulhu",
    "Nyarlathotep",
    "Yog-Sothoth",
    "Shub-Niggurath",
    "Hastur",
    "Dagon",
    "Yig",
    "Tsathoggua",
    "Ghatanothoa"
]

class MenuSystem:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Cthulhu's Dominion")
        self.clock = pygame.time.Clock()
        
        # Load fonts
        try:
            self.font = pygame.font.Font(os.path.join(BASE_DIR, "fonts", "CrimsonText-Regular.ttf"), 48)
            self.small_font = pygame.font.Font(os.path.join(BASE_DIR, "fonts", "CrimsonText-Regular.ttf"), 36)
        except:
            # Fallback to system font if custom font fails to load
            self.font = pygame.font.Font(None, 48)
            self.small_font = pygame.font.Font(None, 36)
            print("Warning: Could not load custom font. Using system font instead.")
        
        self.state = "main_menu"  # States: main_menu, name_entry, game
        self.input_text = ""
        self.error_message = ""
        self.show_overwrite_prompt = False
        
    def draw_button(self, text: str, y: int, selected: bool = False) -> pygame.Rect:
        color = GREEN if selected else WHITE
        text_surface = self.font.render(text, True, color)
        text_rect = text_surface.get_rect(center=(WINDOW_WIDTH // 2, y))
        self.screen.blit(text_surface, text_rect)
        return text_rect
        
    def draw_main_menu(self) -> Dict[str, pygame.Rect]:
        self.screen.fill(BLACK)
        
        title = self.font.render("Cthulhu's Dominion", True, PURPLE)
        title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, 200))
        self.screen.blit(title, title_rect)
        
        buttons = {}
        buttons["new_game"] = self.draw_button("New Game", 350)
        buttons["load_game"] = self.draw_button("Load Game", 450)
        buttons["credits"] = self.draw_button("Credits", 550)
        buttons["quit"] = self.draw_button("Quit", 650)
        
        return buttons
        
    def draw_name_entry(self) -> Dict[str, pygame.Rect]:
        self.screen.fill(BLACK)
        
        title = self.font.render("Name Your Great Old One", True, PURPLE)
        title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, 200))
        self.screen.blit(title, title_rect)
        
        # Input box
        input_surface = self.font.render(self.input_text + "▌", True, WHITE)
        input_rect = input_surface.get_rect(center=(WINDOW_WIDTH // 2, 300))
        self.screen.blit(input_surface, input_rect)
        
        buttons = {}
        buttons["random"] = self.draw_button("Random Name", 400)
        buttons["confirm"] = self.draw_button("Confirm", 500)
        buttons["back"] = self.draw_button("Back to Menu", 600)
        
        if self.error_message:
            error_surface = self.small_font.render(self.error_message, True, (255, 0, 0))
            error_rect = error_surface.get_rect(center=(WINDOW_WIDTH // 2, 700))
            self.screen.blit(error_surface, error_rect)
            
        return buttons
        
    def draw_overwrite_prompt(self) -> Dict[str, pygame.Rect]:
        # Draw semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        overlay.fill(BLACK)
        overlay.set_alpha(128)
        self.screen.blit(overlay, (0, 0))
        
        # Draw prompt box
        prompt_box = pygame.Rect(WINDOW_WIDTH // 4, WINDOW_HEIGHT // 3,
                               WINDOW_WIDTH // 2, WINDOW_HEIGHT // 3)
        pygame.draw.rect(self.screen, BLACK, prompt_box)
        pygame.draw.rect(self.screen, WHITE, prompt_box, 2)
        
        # Draw text
        text = self.small_font.render("Save game already exists. Overwrite?", True, WHITE)
        text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 50))
        self.screen.blit(text, text_rect)
        
        buttons = {}
        buttons["yes"] = self.draw_button("Yes", WINDOW_HEIGHT // 2 + 25)
        buttons["no"] = self.draw_button("No", WINDOW_HEIGHT // 2 + 75)
        
        return buttons
        
    def save_game(self, name: str, overwrite: bool = False) -> bool:
        filepath = os.path.join(BASE_DIR, "Games", f"{name}.json")
        
        if os.path.exists(filepath) and not overwrite:
            return False
            
        game_data = {
            "player_name": name,
            "sanity": 0,
            "resources": {},
            "upgrades": {}
        }
        
        with open(filepath, "w") as f:
            json.dump(game_data, f, indent=4)
            
        return True
        
    def load_game(self, name: str) -> Optional[Dict[str, Any]]:
        filepath = os.path.join(BASE_DIR, "Games", f"{name}.json")
        
        if not os.path.exists(filepath):
            return None
            
        with open(filepath, "r") as f:
            return json.load(f)
            
    def draw_load_game(self) -> Dict[str, pygame.Rect]:
        self.screen.fill(BLACK)
        
        title = self.font.render("Load Game", True, PURPLE)
        title_rect = title.get_rect(center=(WINDOW_WIDTH // 2, 100))
        self.screen.blit(title, title_rect)
        
        buttons = {}
        y = 200
        
        # Get list of save files
        save_files = []
        for file in os.listdir(os.path.join(BASE_DIR, "Games")):
            if file.endswith(".json"):
                save_files.append(file[:-5])  # Remove .json extension
        
        if not save_files:
            text = self.font.render("No saved games found", True, WHITE)
            text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, y))
            self.screen.blit(text, text_rect)
        else:
            for save in save_files:
                buttons[save] = self.draw_button(save, y)
                y += 70
        
        buttons["back"] = self.draw_button("Back to Menu", y + 50)
        return buttons
        
    def run(self):
        running = True
        selected_button = None
        
        while running:
            mouse_pos = pygame.mouse.get_pos()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.show_overwrite_prompt:
                        buttons = self.draw_overwrite_prompt()
                        if buttons["yes"].collidepoint(mouse_pos):
                            self.save_game(self.input_text, overwrite=True)
                            return ("start_game", self.input_text)
                        elif buttons["no"].collidepoint(mouse_pos):
                            self.show_overwrite_prompt = False
                            
                    elif self.state == "main_menu":
                        buttons = self.draw_main_menu()
                        if buttons["new_game"].collidepoint(mouse_pos):
                            self.state = "name_entry"
                            self.input_text = ""
                        elif buttons["load_game"].collidepoint(mouse_pos):
                            self.state = "load_game"
                        elif buttons["credits"].collidepoint(mouse_pos):
                            # TODO: Implement credits screen
                            pass
                        elif buttons["quit"].collidepoint(mouse_pos):
                            running = False
                            
                    elif self.state == "load_game":
                        buttons = self.draw_load_game()
                        if buttons["back"].collidepoint(mouse_pos):
                            self.state = "main_menu"
                        else:
                            for save_name, button in buttons.items():
                                if save_name != "back" and button.collidepoint(mouse_pos):
                                    return ("start_game", save_name)
                            
                    elif self.state == "name_entry":
                        buttons = self.draw_name_entry()
                        if buttons["random"].collidepoint(mouse_pos):
                            self.input_text = random.choice(GREAT_OLD_ONES)
                        elif buttons["confirm"].collidepoint(mouse_pos):
                            if len(self.input_text.strip()) == 0:
                                self.error_message = "Please enter a name"
                            else:
                                if not self.save_game(self.input_text):
                                    self.show_overwrite_prompt = True
                                else:
                                    return ("start_game", self.input_text)
                        elif buttons["back"].collidepoint(mouse_pos):
                            self.state = "main_menu"
                            
                elif event.type == pygame.KEYDOWN and self.state == "name_entry":
                    if event.key == pygame.K_RETURN:
                        if len(self.input_text.strip()) > 0:
                            if not self.save_game(self.input_text):
                                self.show_overwrite_prompt = True
                            else:
                                return ("start_game", self.input_text)
                    elif event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                    else:
                        if len(self.input_text) < 20:  # Max name length
                            self.input_text += event.unicode
                            
            # Draw current state
            if self.state == "main_menu":
                buttons = self.draw_main_menu()
            elif self.state == "name_entry":
                buttons = self.draw_name_entry()
            elif self.state == "load_game":
                buttons = self.draw_load_game()
                
            if self.show_overwrite_prompt:
                self.draw_overwrite_prompt()
                
            pygame.display.flip()
            self.clock.tick(FPS)
            
        return ("quit", None)

if __name__ == "__main__":
    menu = MenuSystem()
    result = menu.run()
    print(result) 