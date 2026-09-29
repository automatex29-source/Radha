"""Style presets for generated images and videos.

A preset adds prompt words that steer the image model toward a look (an ad, a
movie, a 3D animation...) and, for videos, picks the shot list, transitions,
pacing and extras such as movie letterbox bars.
"""
from typing import Dict, List

IMAGE_STYLES: Dict[str, str] = {
    "photo": "professional photograph, natural light, sharp focus, highly detailed, realistic",
    "cinematic": "cinematic movie still, anamorphic lens, dramatic lighting, film grain, color graded, "
                 "epic composition",
    "ad": "premium commercial advertising photo, studio lighting, clean composition, vibrant, glossy, "
          "space for headline text, magazine quality",
    "product": "studio product photography, soft box lighting, seamless background, crisp reflections, 8k detail",
    "poster": "bold graphic poster design, striking composition, strong color contrast, dramatic, print quality",
    "logo": "minimal modern flat vector logo, simple iconic shape, centered, plain white background, no mockup",
    "3d_animation": "3D animated film still, Pixar style, soft global illumination, vibrant colors, "
                    "expressive characters, subsurface scattering",
    "anime": "anime key visual, detailed hand-painted background, cel shading, vivid colors, Studio Ghibli inspired",
    "cartoon": "2D cartoon illustration, bold clean outlines, flat vibrant colors, playful",
    "illustration": "digital illustration, painterly, rich detail, artstation quality",
    "watercolor": "watercolor painting, soft washes, textured paper, delicate",
    "oil_painting": "oil painting, visible brush strokes, classical composition, museum quality",
    "pixel_art": "detailed pixel art, 16-bit retro game style, crisp pixels",
    "fantasy": "epic fantasy concept art, magical atmosphere, volumetric light, highly detailed",
    "sci_fi": "futuristic sci-fi concept art, neon accents, sleek technology, cinematic lighting",
    "thumbnail": "eye-catching YouTube thumbnail style, bold subject, high contrast, saturated colors, "
                 "expressive, clean background",
    "social_post": "trendy social media post aesthetic, bright, clean, eye-catching, modern",
    "food": "mouth-watering food photography, shallow depth of field, warm light, fresh ingredients, styled",
    "real_estate": "architectural real estate photography, wide angle, bright natural light, inviting interior",
    "fashion": "high fashion editorial photo, vogue style, dramatic studio lighting, elegant pose",
}

# shots: camera shots used when the model gives one prompt and no scene list.
# transitions: ffmpeg xfade names used in turn. pace: seconds per scene. zoom: camera move strength.
VIDEO_STYLES: Dict[str, dict] = {
    "movie": {"image": "cinematic", "transitions": ["fadeblack", "fade"], "pace": 3.5, "zoom": 0.12,
              "letterbox": True,
              "shots": ["wide establishing shot", "medium shot of the main character", "tense close-up",
                        "dynamic action shot", "dramatic climax", "final wide shot at sunset"]},
    "trailer": {"image": "cinematic", "transitions": ["fadeblack"], "pace": 2.6, "zoom": 0.18, "letterbox": True,
                "shots": ["mysterious wide shot", "hero close-up", "explosive action moment", "villain silhouette",
                          "epic confrontation", "title card style final shot"]},
    "ad": {"image": "ad", "transitions": ["slideleft", "smoothleft", "wipeleft"], "pace": 2.4, "zoom": 0.16,
           "shots": ["hero shot of the product", "person happily using the product", "close-up of key detail",
                     "product in a stylish lifestyle setting", "final hero shot with clean space for text"]},
    "product": {"image": "product", "transitions": ["fade", "smoothleft"], "pace": 3.0, "zoom": 0.14,
                "shots": ["front hero view", "three quarter angle", "macro detail of materials",
                          "product in use", "final hero view"]},
    "3d_animation": {"image": "3d_animation", "transitions": ["circleopen", "fade", "radial"], "pace": 3.0,
                     "zoom": 0.14, "shots": ["wide shot of the colorful world", "cute main character smiling",
                                             "character on an adventure", "funny moment", "happy ending"]},
    "anime": {"image": "anime", "transitions": ["fade", "wipeleft", "fadewhite"], "pace": 3.0, "zoom": 0.12,
              "shots": ["scenic wide shot", "character close-up with wind in hair", "dynamic action pose",
                        "emotional moment", "beautiful sky ending"]},
    "cartoon": {"image": "cartoon", "transitions": ["circleopen", "slideright", "fade"], "pace": 2.8, "zoom": 0.14,
                "shots": ["wide funny scene", "character reaction", "silly action", "surprise moment",
                          "happy ending"]},
    "music_video": {"image": "cinematic", "transitions": ["fadewhite", "zoomin", "fade"], "pace": 2.2,
                    "zoom": 0.2, "suffix": "neon lights, moody concert lighting, vivid colors",
                    "shots": ["singer on stage", "crowd with lights", "moody close-up", "dancers in motion",
                              "stage lights explosion"]},
    "documentary": {"image": "photo", "transitions": ["dissolve", "fade"], "pace": 4.0, "zoom": 0.1,
                    "suffix": "National Geographic documentary photography",
                    "shots": ["sweeping landscape", "subject in natural habitat", "intimate detail",
                              "people at work", "calm closing view"]},
    "travel": {"image": "photo", "transitions": ["slideleft", "fade"], "pace": 2.8, "zoom": 0.16,
               "suffix": "stunning travel photography, golden hour",
               "shots": ["aerial view of the destination", "famous landmark", "local street life", "local food",
                         "sunset view"]},
    "real_estate": {"image": "real_estate", "transitions": ["fade", "smoothleft"], "pace": 3.5, "zoom": 0.12,
                    "shots": ["exterior front view", "living room", "kitchen", "bedroom", "view from balcony"]},
    "food": {"image": "food", "transitions": ["fade", "slideleft"], "pace": 2.8, "zoom": 0.16,
             "shots": ["hero shot of the dish", "fresh ingredients", "cooking in action", "close-up texture",
                       "served table"]},
    "fashion": {"image": "fashion", "transitions": ["fadeblack", "slideleft"], "pace": 2.6, "zoom": 0.16,
                "shots": ["full body pose", "detail of outfit", "walking on runway", "close-up portrait",
                          "final pose"]},
    "social_reel": {"image": "social_post", "transitions": ["slideup", "zoomin", "slideleft"], "pace": 2.0,
                    "zoom": 0.2, "portrait": True,
                    "shots": ["eye-catching opening", "main subject", "fun detail", "reaction moment",
                              "final call to action"]},
    "explainer": {"image": "illustration", "transitions": ["slideleft"], "pace": 3.5, "zoom": 0.08,
                  "suffix": "clean flat infographic style, simple shapes, clear",
                  "shots": ["the problem", "the idea", "how it works", "the benefit", "summary"]},
}
VIDEO_STYLES["cinematic"] = VIDEO_STYLES["movie"]
DEFAULT_VIDEO_STYLE = "movie"


def image_style_names() -> List[str]:
    return list(IMAGE_STYLES)


def video_style_names() -> List[str]:
    return [k for k in VIDEO_STYLES if k != "cinematic"]


def styled_image_prompt(prompt: str, style: str) -> str:
    words = IMAGE_STYLES.get((style or "").lower())
    return f"{prompt}. {words}" if words else prompt


def video_style(style: str) -> dict:
    return VIDEO_STYLES.get((style or "").lower().replace(" ", "_"), VIDEO_STYLES[DEFAULT_VIDEO_STYLE])


def video_scene_words(style: str) -> str:
    cfg = video_style(style)
    extra = cfg.get("suffix")
    look = IMAGE_STYLES[cfg["image"]]
    return f"{look}, {extra}" if extra else look
