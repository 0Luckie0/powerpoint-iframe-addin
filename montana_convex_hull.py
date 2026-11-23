import os
import re

import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
from shapely.geometry import MultiPoint


# 1. DOSYA YOLLARI
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIONS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PROJECT_DIR = os.path.abspath(os.path.join(STATIONS_DIR, ".."))

SEARCH_DIRS = [PROJECT_DIR, SCRIPT_DIR, STATIONS_DIR, os.getcwd()]


def find_file(*parts):
    """Dosyayı PROJECT_DIR'de, bulamazsa yakın klasörlerde arar."""
    tried = []
    for base in SEARCH_DIRS:
        candidate = os.path.join(base, *parts)
        tried.append(candidate)
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError("Dosya bulunamadı. Denenen yollar:\n  " + "\n  ".join(tried))


SHAPEFILE_PATH = find_file("cb_2024_us_state_500k", "cb_2024_us_state_500k.shp")
CSV_PATH = find_file("Montana_stations.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "Montana_Convex_Hull.png")


# 2. AYARLAR

STATE_NAME = "Montana"
MAP_CRS = 5070            # NAD83 / Conus Albers 
STATION_CRS = 4326        

# Çıktı boyutu: görselle aynı 856 x 605 piksel (100 dpi'da).
# OUTPUT_DPI değerini artırın (örn. 300) - yerleşim aynı kalır, sadece çözünürlük artar.
W_PX, H_PX = 856, 605
DESIGN_DPI = 100
OUTPUT_DPI = 300

M_PER_PX = 1000.0 / 0.72                # 100 km = 72 px  ->  1 px = 1388.89 m
MT_CENTER_PX = (436.5, 275.5)           

# Renkler 
HULL_FILL = "#E5B636"
STATION_BLUE = "#1354DE"
LINE_BLACK = "#000000"

# Yazı tipi 
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Tahoma", "Segoe UI", "Arial", "DejaVu Sans"]
plt.rcParams["hatch.linewidth"] = 0.3


def px_to_pt(px):
    
    return px * 72.0 / DESIGN_DPI

# 3. VERİYİ OKU
# Montana sınırı 
states = gpd.read_file(SHAPEFILE_PATH)
montana = states[states["NAME"] == STATE_NAME].to_crs(epsg=MAP_CRS)
if montana.empty:
    raise ValueError(f"Shapefile içinde '{STATE_NAME}' bulunamadı.")


# GPS istasyonları 
def parse_point(geom_str):
    """'POINT (lon lat)' -> (lon, lat)"""
    nums = re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(geom_str))
    if len(nums) < 2:
        return None
    return float(nums[0]), float(nums[1])


df = pd.read_csv(CSV_PATH, sep=None, engine="python")
df.columns = df.columns.str.strip()

records = []
for _, row in df.iterrows():
    if pd.isna(row["geometry"]):
        continue
    xy = parse_point(row["geometry"])
    if xy is None:
        continue
    records.append({"Station": str(row["Station"]).strip(), "lon": xy[0], "lat": xy[1]})

stations = pd.DataFrame(records)
stations_gdf = gpd.GeoDataFrame(
    stations,
    geometry=gpd.points_from_xy(stations["lon"], stations["lat"]),
    crs=f"EPSG:{STATION_CRS}",
).to_crs(epsg=MAP_CRS)

n_stations = len(stations_gdf)


# 4. CONVEX HULL ve ALAN 

hull = MultiPoint(list(stations_gdf.geometry)).convex_hull
hull_area_km2 = hull.area / 1e6

print(f"Montana GPS istasyon sayısı : {n_stations}")
print(f"Convex hull alanı           : {hull_area_km2:.3f} km²")


# 5. FİGÜR

fig = plt.figure(figsize=(W_PX / DESIGN_DPI, H_PX / DESIGN_DPI), dpi=DESIGN_DPI, facecolor="white")

# 5a. Harita ekseni: tüm figürü kaplar, (EPSG:5070)
ax = fig.add_axes([0, 0, 1, 1])
ax.axis("off")

minx, miny, maxx, maxy = montana.total_bounds
cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
ax.set_xlim(cx - MT_CENTER_PX[0] * M_PER_PX, cx + (W_PX - MT_CENTER_PX[0]) * M_PER_PX)
ax.set_ylim(cy - (H_PX - MT_CENTER_PX[1]) * M_PER_PX, cy + MT_CENTER_PX[1] * M_PER_PX)
# (limit oranı figür oranıyla birebir aynı olduğundan set_aspect gerekmez: 1 px = 1388.89 m)


def draw_polygon_outline(axis, geom, **kwargs):
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    for p in polys:
        axis.add_patch(Polygon(list(p.exterior.coords), closed=True, fill=False, **kwargs))
        for ring in p.interiors:
            axis.add_patch(Polygon(list(ring.coords), closed=True, fill=False, **kwargs))


# Çizim sırası (görseldeki gibi): hull (altta) -> Montana sınırı (üstte, dolgusuz) -> istasyonlar
ax.add_patch(Polygon(list(hull.exterior.coords), closed=True,
                     facecolor=HULL_FILL, edgecolor=LINE_BLACK, linewidth=0.4,
                     joinstyle="round", zorder=2))

for geom in montana.geometry:
    draw_polygon_outline(ax, geom, edgecolor=LINE_BLACK, linewidth=0.52,
                         joinstyle="round", zorder=3)

STATION_S = px_to_pt(6.4) ** 2    
ax.scatter(stations_gdf.geometry.x, stations_gdf.geometry.y,
           s=STATION_S, c=STATION_BLUE, edgecolors="#232323", linewidths=0.15, zorder=4)

# 5b. Arayüz ekseni: piksel koordinatları (sol-üst = 0,0) - başlık, ok, ölçek, gösterge
ui = fig.add_axes([0, 0, 1, 1], zorder=10)
ui.set_xlim(0, W_PX)
ui.set_ylim(H_PX, 0)
ui.axis("off")

#  Başlık 
ui.text(421.5, 39.5, "Montana Convex Hull", ha="center", va="baseline",
        fontsize=18, color="black")

#  Kuzey oku (sol yarısı taralı) 
tip, bl, notch, br = (812.5, 44.0), (794.0, 91.5), (812.5, 73.0), (831.0, 91.5)
ui.add_patch(Polygon([tip, bl, notch], closed=True, facecolor="white",
                     edgecolor="#8a8a8a", hatch="////////////", linewidth=0))
ui.add_patch(Polygon([tip, bl, notch, br], closed=True, fill=False,
                     edgecolor="black", linewidth=1.35, joinstyle="miter"))

#  Ölçek çubuğu: 0 - 100 - 200 km 
BAR_X0, BAR_Y0, SEG_PX, BAR_H = 25.0, 570.5, 72.0, 9.0
ui.add_patch(Rectangle((BAR_X0, BAR_Y0), SEG_PX, BAR_H,
                       facecolor="black", edgecolor="black", linewidth=0.5))
ui.add_patch(Rectangle((BAR_X0 + SEG_PX, BAR_Y0), SEG_PX, BAR_H,
                       facecolor="white", edgecolor="black", linewidth=0.5))

LABEL_Y = 561.5
ui.text(BAR_X0 - 0.5, LABEL_Y, "0", ha="center", va="baseline", fontsize=9)
ui.text(BAR_X0 + SEG_PX - 0.5, LABEL_Y, "100", ha="center", va="baseline", fontsize=9)
t200 = ui.text(BAR_X0 + 2 * SEG_PX - 0.5, LABEL_Y, "200", ha="center", va="baseline", fontsize=9)

def text_right_edge(text_artist):
    """Yazının sağ kenarının piksel konumu (figür 100 dpi iken 1 birim = 1 px)."""
    try:
        renderer = fig.canvas.get_renderer()
    except AttributeError:
        renderer = None
    return text_artist.get_window_extent(renderer).x1


# "km" yazısı "200"ün hemen sağına, bir boşluk bırakılarak yazılır 
ui.text(text_right_edge(t200) + 3.9, LABEL_Y, "km", ha="left", va="baseline", fontsize=9)

#  Gösterge (sağ alt, çerçevesiz) 
LEG_TEXT_X = 685.0
LEG_FONT = 9
rows = [
    (539.5, "Montana Boundary"),
    (559.5, f"Montana GPS Stations = {n_stations}"),
    (578.5, f"Montana = {hull_area_km2:.3f} km²"),
]
legend_texts = [ui.text(LEG_TEXT_X, baseline, label, ha="left", va="baseline", fontsize=LEG_FONT)
                for baseline, label in rows]

# Tahoma yoksa yedek font daha geniş olabilir: gösterge yazısı kenardan taşıyorsa küçült
right_limit = W_PX - 3
widest = max(text_right_edge(t) for t in legend_texts)
if widest > right_limit:
    shrink = (right_limit - LEG_TEXT_X) / (widest - LEG_TEXT_X)
    for t in legend_texts:
        t.set_fontsize(LEG_FONT * shrink)

# Montana Boundary simgesi: beyaz dolgu + ince siyah çerçeve
ui.add_patch(Rectangle((659.5, 530.5), 19.5, 11.5, facecolor="white", edgecolor="#232323", linewidth=0.58))
# GPS istasyonu simgesi: mavi nokta
ui.scatter([669.5], [555.0], s=STATION_S, c=STATION_BLUE, edgecolors="#232323", linewidths=0.15, zorder=5)
# Hull simgesi: altın sarısı dolgu + ince siyah çerçeve
ui.add_patch(Rectangle((659.5, 567.5), 19.5, 11.5, facecolor=HULL_FILL, edgecolor="#232323", linewidth=0.45))

# 6. KAYDET ve GÖSTER
fig.savefig(OUTPUT_PNG, dpi=OUTPUT_DPI, facecolor="white")
print(f"Harita kaydedildi: {OUTPUT_PNG}")
plt.show()
