import pygame
import sys
import time
from dataclasses import dataclass
from typing import Dict, List
from upgrades import UpgradeManager
from menu import MenuSystem
import json
import os

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
RED = (255, 0, 0)
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

@dataclass
class Resource:
    name: str
    base_cost: float
    base_production: float
    production_time: float
    manager_name: str
    unlock_cost: float
    count: int = 0
    progress: float = 0
    is_processing: bool = False
    has_manager: bool = False
    level: int = 1
    manager_cost: float = 1000
    is_unlocked: bool = False

class Game:
    def __init__(self, player_name: str = None, load_data: Dict = None):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(f"Cthulhu's Dominion - {player_name}")
        self.clock = pygame.time.Clock()
        
        # Load fonts
        try:
            if getattr(sys, 'frozen', False):
                # If we're running as a bundled executable
                font_path = os.path.join(sys._MEIPASS, "fonts", "CrimsonText-Regular.ttf")
            else:
                # If we're running as a script
                font_path = os.path.join(BASE_DIR, "fonts", "CrimsonText-Regular.ttf")
            
            self.font = pygame.font.Font(font_path, 32)
            self.small_font = pygame.font.Font(font_path, 20)
        except Exception as e:
            print(f"Warning: Could not load custom font: {e}")
            # Fallback to system font if custom font fails to load
            self.font = pygame.font.Font(None, 32)
            self.small_font = pygame.font.Font(None, 20)
        
        # Game state
        self.player_name = player_name
        self.sanity = 0
        self.upgrade_manager = UpgradeManager()
        self.upgrade_scroll = 0  # Track scroll position
        self.max_upgrade_scroll = 0  # Maximum scroll value
        self.worlds_destroyed = 0  # Counter for worlds destroyed
        self.show_world_end = False  # Flag for showing the world end popup
        
        self.resources = {
            "cultists": Resource("Cultists", 10, 1, 2.0, "Cult Leader", unlock_cost=5, manager_cost=25, is_unlocked=True),
            "ancient_tomes": Resource("Ancient Tomes", 50, 5, 3.0, "Mad Librarian", unlock_cost=25, manager_cost=125),
            "eldritch_artifacts": Resource("Eldritch Artifacts", 200, 15, 4.0, "Relic Hunter", unlock_cost=75, manager_cost=375),
            "sacrifices": Resource("Sacrifices", 1000, 50, 5.0, "High Priest", unlock_cost=250, manager_cost=1250),
            "dark_rituals": Resource("Dark Rituals", 5000, 200, 6.0, "Ritual Master", unlock_cost=1000, manager_cost=5000),
            "cosmic_energy": Resource("Cosmic Energy", 20000, 750, 7.0, "Star Priest", unlock_cost=3750, manager_cost=18750),
            "elder_signs": Resource("Elder Signs", 100000, 3000, 8.0, "Sign Keeper", unlock_cost=15000, manager_cost=75000),
            "dimensional_gates": Resource("Dimensional Gates", 500000, 10000, 9.0, "Gate Keeper", unlock_cost=50000, manager_cost=250000),
            "star_spawn": Resource("Star Spawn", 2000000, 50000, 10.0, "Spawn Master", unlock_cost=250000, manager_cost=1250000),
            "great_old_ones": Resource("Great Old Ones", 10000000, 200000, 12.0, "Elder Priest", unlock_cost=1000000, manager_cost=5000000)
        }
        
        if load_data:
            self.load_game_state(load_data)

    def load_game_state(self, data: Dict):
        self.player_name = data["player_name"]
        self.sanity = data["sanity"]
        self.worlds_destroyed = data.get("worlds_destroyed", 0)  # Load worlds destroyed count
        
        # Load resources
        for resource_name, resource_data in data.get("resources", {}).items():
            if resource_name in self.resources:
                resource = self.resources[resource_name]
                for key, value in resource_data.items():
                    setattr(resource, key, value)
                # Start processing if resource has a manager
                if resource.has_manager and resource.is_unlocked:
                    resource.is_processing = True
        
        # Load purchased upgrades
        for upgrade_id in data.get("upgrades", {}):
            if upgrade_id in self.upgrade_manager.upgrades:
                self.upgrade_manager.upgrades[upgrade_id].purchased = True

    def save_game_state(self):
        game_data = {
            "player_name": self.player_name,
            "sanity": self.sanity,
            "worlds_destroyed": self.worlds_destroyed,  # Save worlds destroyed count
            "resources": {},
            "upgrades": {}
        }
        
        # Save resources
        for name, resource in self.resources.items():
            game_data["resources"][name] = {
                "count": resource.count,
                "level": resource.level,
                "has_manager": resource.has_manager,
                "is_unlocked": resource.is_unlocked
            }
        
        # Save purchased upgrades
        for upgrade_id, upgrade in self.upgrade_manager.upgrades.items():
            if upgrade.purchased:
                game_data["upgrades"][upgrade_id] = True
            
        filepath = os.path.join(BASE_DIR, "Games", f"{self.player_name}.json")
        with open(filepath, "w") as f:
            json.dump(game_data, f, indent=4)

    def draw_resource_button(self, resource, y):
        # Create button rectangle - moved left to align with player name
        button = pygame.Rect(20, y, 350, 52)  # Reduced height from 70 to 52 (75% of original)
        
        # Draw shadow
        shadow_rect = button.copy()
        shadow_rect.x += 2
        shadow_rect.y += 2
        pygame.draw.rect(self.screen, (0, 0, 0, 100), shadow_rect)
        
        # Draw button background with gradient (dark purple to darker purple)
        # If resource is unlocked, add green tint
        for i in range(button.height):
            if resource.is_unlocked:
                color = (
                    int(40 + (i/button.height) * 20),  # R
                    int(20 + (i/button.height) * 10),  # G (added green tint)
                    int(60 + (i/button.height) * 30),  # B
                    255                                # A
                )
            else:
                color = (
                    int(40 + (i/button.height) * 20),  # R
                    0,                                  # G
                    int(60 + (i/button.height) * 30),  # B
                    255                                # A
                )
            pygame.draw.line(self.screen, color,
                           (button.x, button.y + i),
                           (button.x + button.width, button.y + i))
        
        # Draw button border
        pygame.draw.rect(self.screen, WHITE, button, 1)
        
        # Calculate production rate
        production_multiplier, speed_multiplier = self.upgrade_manager.get_multiplier(resource.name)
        production_rate = resource.base_production * resource.level * production_multiplier
        
        # Draw resource name with glow effect (left-aligned, vertically centered)
        name_text = self.font.render(resource.name, True, WHITE)
        name_rect = name_text.get_rect(x=button.x + 10, centery=button.centery)  # Vertically centered
        
        # Draw text glow
        glow_surface = pygame.Surface((button.width, button.height), pygame.SRCALPHA)
        glow_surface.blit(name_text, (0, 0))
        pygame.draw.rect(glow_surface, (255, 255, 255, 30), (0, 0, button.width, button.height))
        self.screen.blit(glow_surface, (button.x, button.y))
        
        self.screen.blit(name_text, name_rect)
        
        # Draw production rate with glow effect (right-aligned, vertically centered)
        rate_text = self.small_font.render(f"{int(production_rate)} Sanity", True, WHITE)
        rate_rect = rate_text.get_rect(right=button.right - 10, centery=button.centery)  # Vertically centered
        
        # Draw rate text glow
        glow_surface = pygame.Surface((button.width, button.height), pygame.SRCALPHA)
        glow_surface.blit(rate_text, (0, 0))
        pygame.draw.rect(glow_surface, (255, 255, 255, 30), (0, 0, button.width, button.height))
        self.screen.blit(glow_surface, (button.x, button.y))
        
        self.screen.blit(rate_text, rate_rect)
        
        # Draw progress bar with glow effect
        progress_ratio = resource.progress / resource.production_time
        progress_width = int(button.width * progress_ratio)
        
        if progress_width > 0:
            # Draw progress bar shadow
            progress_shadow = pygame.Rect(button.x, button.bottom - 12, progress_width, 8)  # Adjusted to bottom
            progress_shadow.x += 1
            progress_shadow.y += 1
            pygame.draw.rect(self.screen, (0, 0, 0, 100), progress_shadow)
            
            # Draw progress bar with gradient (bright green to darker green)
            for i in range(8):  # Reduced height from 10 to 8
                color = (
                    0,                                  # R
                    int(200 + (i/8) * 55),             # G
                    0,                                  # B
                    255                                # A
                )
                pygame.draw.line(self.screen, color,
                               (button.x, button.bottom - 12 + i),
                               (button.x + progress_width, button.bottom - 12 + i))
            
            # Draw progress bar glow
            glow_surface = pygame.Surface((progress_width, 8), pygame.SRCALPHA)  # Reduced height from 10 to 8
            pygame.draw.rect(glow_surface, (0, 255, 0, 30), (0, 0, progress_width, 8))
            self.screen.blit(glow_surface, (button.x, button.bottom - 12))
        
        # Draw manager button if resource is unlocked
        if resource.is_unlocked:
            manager_button = pygame.Rect(420, y, 300, 52)  # Adjusted height to match resource button
            
            # Draw manager button shadow
            manager_shadow = manager_button.copy()
            manager_shadow.x += 2
            manager_shadow.y += 2
            pygame.draw.rect(self.screen, (0, 0, 0, 100), manager_shadow)
            
            # Draw manager button with gradient
            # If manager is hired, always use green. Otherwise, use green/red based on affordability
            if resource.has_manager:
                color = GREEN
            else:
                color = GREEN if self.sanity >= resource.manager_cost else RED
                
            for i in range(manager_button.height):
                gradient_color = (
                    int(color[0] * (1 - i/manager_button.height)),  # R
                    int(color[1] * (1 - i/manager_button.height)),  # G
                    int(color[2] * (1 - i/manager_button.height)),  # B
                    255                                      # A
                )
                pygame.draw.line(self.screen, gradient_color,
                               (manager_button.x, manager_button.y + i),
                               (manager_button.x + manager_button.width, manager_button.y + i))
            
            # Draw manager button border
            pygame.draw.rect(self.screen, WHITE, manager_button, 1)
            
            # Draw manager text with glow effect
            if not resource.has_manager:
                manager_text = self.font.render(f"{resource.manager_name}: {int(resource.manager_cost)}", True, WHITE)
            else:
                manager_text = self.font.render(f"{resource.manager_name} Hired!", True, GREEN)
            
            text_rect = manager_text.get_rect(center=manager_button.center)
            
            # Draw text glow
            glow_surface = pygame.Surface((manager_button.width, manager_button.height), pygame.SRCALPHA)
            glow_surface.blit(manager_text, (0, 0))
            pygame.draw.rect(glow_surface, (255, 255, 255, 30), (0, 0, manager_button.width, manager_button.height))
            self.screen.blit(glow_surface, (manager_button.x, manager_button.y))
            
            self.screen.blit(manager_text, text_rect)

    def update_resource(self, resource: Resource, dt: float):
        if resource.is_processing:
            # Apply speed multiplier to dt
            production_multiplier, speed_multiplier = self.upgrade_manager.get_multiplier(resource.name)
            
            # For very high speeds, we'll process multiple cycles at once
            resource.progress += dt * speed_multiplier
            cycles_completed = int(resource.progress / resource.production_time)
            
            if cycles_completed > 0:
                production = resource.base_production * resource.level * production_multiplier * cycles_completed
                resource.count += production
                self.sanity += production
                resource.progress = resource.progress % resource.production_time
                
                if not resource.has_manager:
                    resource.is_processing = False

    def draw_upgrades(self):
        # Define upgrade panel area with shadow
        upgrade_area = pygame.Rect(800, 50, 300, WINDOW_HEIGHT - 100)
        shadow_rect = upgrade_area.copy()
        shadow_rect.x += 4
        shadow_rect.y += 4
        pygame.draw.rect(self.screen, (0, 0, 0, 100), shadow_rect)
        
        # Draw the main panel with solid dark blue color
        pygame.draw.rect(self.screen, (0, 0, 50), upgrade_area)
        
        # Draw border
        pygame.draw.rect(self.screen, WHITE, upgrade_area, 2)
        
        # Create a clipping rect for the upgrade area
        pygame.display.get_surface().set_clip(upgrade_area)
        
        # Draw title with glow effect
        title = self.font.render("Upgrades", True, WHITE)
        title_rect = title.get_rect(center=(upgrade_area.centerx, upgrade_area.y + 20))
        
        # Draw title glow
        glow_surface = pygame.Surface((upgrade_area.width, 40), pygame.SRCALPHA)
        glow_surface.blit(title, (0, 0))
        pygame.draw.rect(glow_surface, (255, 255, 255, 30), (0, 0, upgrade_area.width, 40))
        self.screen.blit(glow_surface, (upgrade_area.x, upgrade_area.y))
        
        self.screen.blit(title, title_rect)
        
        # Filter upgrades for unlocked resources only, showing only next upgrade per resource
        available_upgrades = []
        resource_next_upgrades = {}
        
        # First, group upgrades by resource
        for upgrade_id, upgrade in self.upgrade_manager.upgrades.items():
            if not upgrade.purchased:
                # Find the resource key that matches the upgrade's resource name
                for resource_key, resource in self.resources.items():
                    if resource_key.lower() == upgrade.resource and resource.is_unlocked:
                        if resource_key not in resource_next_upgrades:
                            resource_next_upgrades[resource_key] = []
                        resource_next_upgrades[resource_key].append((upgrade_id, upgrade))
                        break
        
        # Then, select only the next upgrade for each resource
        for resource_key, upgrades in resource_next_upgrades.items():
            # Sort upgrades by type (speed first, then production)
            speed_upgrades = [u for u in upgrades if "speed" in u[1].upgrade_type.lower()]
            prod_upgrades = [u for u in upgrades if "production" in u[1].upgrade_type.lower()]
            
            # Add next speed upgrade if available
            if speed_upgrades:
                available_upgrades.append(speed_upgrades[0])
            # Add next production upgrade if available
            if prod_upgrades:
                available_upgrades.append(prod_upgrades[0])
        
        # Calculate maximum scroll value
        total_height = len(available_upgrades) * 70  # 70 pixels per upgrade
        visible_height = upgrade_area.height - 70  # Subtract space for title
        self.max_upgrade_scroll = max(0, total_height - visible_height)
        
        # Handle mouse wheel events
        for event in pygame.event.get(pygame.MOUSEWHEEL):
            if upgrade_area.collidepoint(pygame.mouse.get_pos()):
                self.upgrade_scroll = max(0, min(self.max_upgrade_scroll, 
                                               self.upgrade_scroll - event.y * 20))
        
        # Draw upgrades with scrolling
        y = upgrade_area.y + 50 - self.upgrade_scroll
        self.upgrade_buttons = {}  # Store button rectangles for click detection
        
        for upgrade_id, upgrade in available_upgrades:
            # Only draw if the upgrade would be visible
            if y + 70 > upgrade_area.y and y < upgrade_area.bottom:
                # Draw upgrade button with shadow
                button = pygame.Rect(upgrade_area.x + 10, y, upgrade_area.width - 20, 40)
                shadow_rect = button.copy()
                shadow_rect.x += 2
                shadow_rect.y += 2
                pygame.draw.rect(self.screen, (0, 0, 0, 100), shadow_rect)
                
                # Draw button with gradient
                color = GREEN if self.sanity >= upgrade.cost else RED
                for i in range(button.height):
                    gradient_color = (
                        int(color[0] * (1 - i/button.height)),  # R
                        int(color[1] * (1 - i/button.height)),  # G
                        int(color[2] * (1 - i/button.height)),  # B
                        255                                      # A
                    )
                    pygame.draw.line(self.screen, gradient_color,
                                   (button.x, button.y + i),
                                   (button.x + button.width, button.y + i))
                
                # Draw button border with transparency
                border_surface = pygame.Surface((button.width, button.height), pygame.SRCALPHA)
                pygame.draw.rect(border_surface, (255, 255, 255, 100), (0, 0, button.width, button.height), 1)
                self.screen.blit(border_surface, button)
                
                # Store button only if it's within the visible area
                if button.top >= upgrade_area.top and button.bottom <= upgrade_area.bottom:
                    self.upgrade_buttons[upgrade_id] = button
                
                # Draw upgrade text with glow effect
                text = f"{upgrade.name} - {upgrade.cost}"
                upgrade_text = self.small_font.render(text, True, WHITE)
                desc_text = self.small_font.render(upgrade.description, True, WHITE)
                
                text_rect = upgrade_text.get_rect(center=button.center)
                desc_rect = desc_text.get_rect(centerx=upgrade_area.centerx, y=y + 45)
                
                # Only draw text if it's within the visible area
                if text_rect.top >= upgrade_area.top and text_rect.bottom <= upgrade_area.bottom:
                    self.screen.blit(upgrade_text, text_rect)
                if desc_rect.top >= upgrade_area.top and desc_rect.bottom <= upgrade_area.bottom:
                    self.screen.blit(desc_text, desc_rect)
            
            y += 70
        
        # Reset clipping
        pygame.display.get_surface().set_clip(None)
        
        # Draw scroll indicators if needed
        if self.max_upgrade_scroll > 0:
            if self.upgrade_scroll > 0:
                # Draw up arrow with glow
                arrow_points = [
                    (upgrade_area.right - 20, upgrade_area.top + 10),
                    (upgrade_area.right - 10, upgrade_area.top + 20),
                    (upgrade_area.right - 30, upgrade_area.top + 20)
                ]
                pygame.draw.polygon(self.screen, (255, 255, 255, 100), arrow_points)
                pygame.draw.polygon(self.screen, WHITE, arrow_points)
            
            if self.upgrade_scroll < self.max_upgrade_scroll:
                # Draw down arrow with glow
                arrow_points = [
                    (upgrade_area.right - 20, upgrade_area.bottom - 10),
                    (upgrade_area.right - 10, upgrade_area.bottom - 20),
                    (upgrade_area.right - 30, upgrade_area.bottom - 20)
                ]
                pygame.draw.polygon(self.screen, (255, 255, 255, 100), arrow_points)
                pygame.draw.polygon(self.screen, WHITE, arrow_points)

    def check_all_upgrades_purchased(self):
        """Check if all upgrades have been purchased"""
        return all(upgrade.purchased for upgrade in self.upgrade_manager.upgrades.values())

    def reset_game(self):
        """Reset the game state while keeping worlds_destroyed counter"""
        self.sanity = 0
        self.upgrade_scroll = 0
        self.max_upgrade_scroll = 0
        self.worlds_destroyed += 1
        self.show_world_end = False
        
        # Reset resources
        for resource in self.resources.values():
            resource.count = 0
            resource.progress = 0
            resource.is_processing = False
            resource.has_manager = False
            resource.level = 1
            resource.is_unlocked = resource.name.lower().replace(" ", "_") == "cultists"
        
        # Reset upgrades
        self.upgrade_manager = UpgradeManager()

    def draw_world_end_popup(self) -> Dict[str, pygame.Rect]:
        # Draw semi-transparent overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        overlay.fill(BLACK)
        overlay.set_alpha(128)
        self.screen.blit(overlay, (0, 0))
        
        # Draw popup box
        popup_width = 600
        popup_height = 200
        x = (WINDOW_WIDTH - popup_width) // 2
        y = (WINDOW_HEIGHT - popup_height) // 2
        popup_rect = pygame.Rect(x, y, popup_width, popup_height)
        pygame.draw.rect(self.screen, BLACK, popup_rect)
        pygame.draw.rect(self.screen, WHITE, popup_rect, 2)
        
        # Draw text
        text1 = self.font.render("Congratulations! Your Great Old One has devoured this world.", True, WHITE)
        text2 = self.font.render("Would you like Azathoth to devour this worldline", True, WHITE)
        text3 = self.font.render("and spin you up another one?", True, WHITE)
        
        text1_rect = text1.get_rect(centerx=WINDOW_WIDTH // 2, centery=y + 40)
        text2_rect = text2.get_rect(centerx=WINDOW_WIDTH // 2, centery=y + 80)
        text3_rect = text3.get_rect(centerx=WINDOW_WIDTH // 2, centery=y + 120)
        
        self.screen.blit(text1, text1_rect)
        self.screen.blit(text2, text2_rect)
        self.screen.blit(text3, text3_rect)
        
        # Draw buttons
        buttons = {}
        yes_button = pygame.Rect(x + 150, y + 150, 100, 30)
        no_button = pygame.Rect(x + 350, y + 150, 100, 30)
        
        pygame.draw.rect(self.screen, GREEN, yes_button)
        pygame.draw.rect(self.screen, RED, no_button)
        
        yes_text = self.font.render("Yes", True, WHITE)
        no_text = self.font.render("No", True, WHITE)
        
        yes_text_rect = yes_text.get_rect(center=yes_button.center)
        no_text_rect = no_text.get_rect(center=no_button.center)
        
        self.screen.blit(yes_text, yes_text_rect)
        self.screen.blit(no_text, no_text_rect)
        
        buttons["yes"] = yes_button
        buttons["no"] = no_button
        
        return buttons

    def draw(self):
        # Draw black background
        self.screen.fill(BLACK)
        
        # Draw player name with glow effect
        name_text = self.font.render(f"Great Old One: {self.player_name}", True, PURPLE)
        name_rect = name_text.get_rect(topleft=(20, 10))  # Moved up to y=10
        
        # Draw name glow (adjusted to only cover the text area)
        glow_surface = pygame.Surface((name_text.get_width() + 20, name_text.get_height() + 10), pygame.SRCALPHA)
        glow_surface.blit(name_text, (10, 5))
        pygame.draw.rect(glow_surface, (128, 0, 128, 30), (0, 0, glow_surface.get_width(), glow_surface.get_height()))
        self.screen.blit(glow_surface, (10, 5))
        
        self.screen.blit(name_text, name_rect)
        
        # Draw sanity counter in center top (as integer)
        sanity_text = self.font.render(f"Sanity: {int(self.sanity)}", True, WHITE)
        sanity_rect = sanity_text.get_rect(center=(WINDOW_WIDTH // 2, 20))
        self.screen.blit(sanity_text, sanity_rect)
        
        # Draw resources with increased spacing
        y = 50  # Start resources higher to align with upgrades panel
        for resource in self.resources.values():
            if resource.is_unlocked:
                self.draw_resource_button(resource, y)
                y += 68  # Adjusted spacing to match new button height + padding
            else:
                # Draw locked resource with dark appearance
                button = pygame.Rect(20, y, 350, 52)  # Adjusted height to match unlocked buttons
                # Draw shadow
                shadow_rect = button.copy()
                shadow_rect.x += 2
                shadow_rect.y += 2
                pygame.draw.rect(self.screen, (0, 0, 0, 100), shadow_rect)
                
                # Draw dark background with affordability glow
                for i in range(button.height):
                    if self.sanity >= resource.unlock_cost:
                        # Green glow for affordable resources
                        color = (
                            int(20 + (i/button.height) * 10),  # R
                            int(40 + (i/button.height) * 20),  # G (added green glow)
                            int(30 + (i/button.height) * 15),  # B
                            255                                # A
                        )
                    else:
                        # Red glow for unaffordable resources
                        color = (
                            int(40 + (i/button.height) * 20),  # R (added red glow)
                            int(20 + (i/button.height) * 10),  # G
                            int(30 + (i/button.height) * 15),  # B
                            255                                # A
                        )
                    pygame.draw.line(self.screen, color,
                                   (button.x, button.y + i),
                                   (button.x + button.width, button.y + i))
                
                # Draw button border
                border_color = GREEN if self.sanity >= resource.unlock_cost else (100, 100, 100)
                pygame.draw.rect(self.screen, border_color, button, 1)
                
                # Draw locked text (left-aligned, vertically centered)
                text_color = GREEN if self.sanity >= resource.unlock_cost else (100, 100, 100)
                name_text = self.font.render(resource.name, True, text_color)
                name_rect = name_text.get_rect(x=button.x + 10, centery=button.centery)  # Vertically centered
                self.screen.blit(name_text, name_rect)
                
                # Draw unlock cost (right-aligned, vertically centered)
                cost_text = self.small_font.render(f"Unlock: {resource.unlock_cost}", True, text_color)
                cost_rect = cost_text.get_rect(right=button.right - 10, centery=button.centery)  # Vertically centered
                self.screen.blit(cost_text, cost_rect)
                
                y += 68  # Adjusted spacing to match new button height + padding
        
        # Draw upgrades panel
        self.draw_upgrades()
        
        # Draw end game popup if active
        if self.show_world_end:
            self.draw_world_end_popup()
        
        # Update display
        pygame.display.flip()

    def run(self):
        running = True
        last_save = time.time()
        self.upgrade_buttons = {}
        
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            current_time = time.time()
            
            # Auto-save every 60 seconds
            if current_time - last_save >= 60:
                self.save_game_state()
                last_save = current_time
            
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.save_game_state()
                    running = False
                    
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mouse_pos = pygame.mouse.get_pos()
                    
                    if self.show_world_end:
                        buttons = self.draw_world_end_popup()
                        if buttons["yes"].collidepoint(mouse_pos):
                            self.reset_game()
                        elif buttons["no"].collidepoint(mouse_pos):
                            self.show_world_end = False
                        continue
                    
                    # Handle resource clicking
                    y = 50  # Start from the same position as visual buttons
                    for resource in self.resources.values():
                        # Resource button
                        button_rect = pygame.Rect(20, y, 350, 52)  # Updated x position to match visual
                        if button_rect.collidepoint(mouse_pos):
                            if not resource.is_unlocked:
                                if self.sanity >= resource.unlock_cost:
                                    resource.is_unlocked = True
                                    self.sanity -= resource.unlock_cost
                            elif not resource.is_processing:
                                resource.is_processing = True
                                resource.progress = 0
                        
                        # Manager button
                        if resource.is_unlocked:
                            manager_button = pygame.Rect(420, y, 300, 52)  # Updated x position to match visual
                            if manager_button.collidepoint(mouse_pos):
                                if not resource.has_manager and self.sanity >= resource.manager_cost:
                                    resource.has_manager = True
                                    self.sanity -= resource.manager_cost
                                    resource.is_processing = True
                        
                        y += 68
                    
                    # Handle upgrade clicking
                    upgrade_area = pygame.Rect(800, 50, 300, WINDOW_HEIGHT - 100)
                    if upgrade_area.collidepoint(mouse_pos):
                        for upgrade_id, button in self.upgrade_buttons.items():
                            if button.collidepoint(mouse_pos):
                                success, self.sanity = self.upgrade_manager.purchase(upgrade_id, self.sanity)
                                if success and self.check_all_upgrades_purchased():
                                    self.show_world_end = True
                                break

            # Update
            for resource in self.resources.values():
                if resource.is_unlocked:
                    self.update_resource(resource, dt)

            # Draw
            self.draw()

def main():
    menu = MenuSystem()
    action, player_name = menu.run()
    
    if action == "start_game":
        # Load existing game or start new one
        game_data = None
        save_file = os.path.join(BASE_DIR, "Games", f"{player_name}.json")
        if os.path.exists(save_file):
            with open(save_file, "r") as f:
                game_data = json.load(f)
        
        game = Game(player_name, game_data)
        game.run()
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main() 