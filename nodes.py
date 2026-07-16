import json


class SCG_Prompt_Forge:
    """ComfyUI node that steps through the prompt batch built in the forge overlay.

    ``prompt_batch`` is a hidden widget written by the overlay:
    ``{"format": "paragraph", "prompts": ["...", ...]}``. Each queue run emits
    ``prompts[index % count]``; set the index widget's control to *increment*
    and queue N runs to burn through the batch one prompt at a time.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt_batch": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": json.dumps({"format": "paragraph",
                                               "prompts": []}),
                    },
                ),
                "index": ("INT", {"default": 0, "min": 0,
                                  "max": 0xffffffffffffffff,
                                  "control_after_generate": True}),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "INT")
    RETURN_NAMES = ("prompt", "index", "count")
    FUNCTION = "pick"
    CATEGORY = "SCG/PromptForge"

    def pick(self, prompt_batch, index):
        try:
            data = json.loads(prompt_batch or "")
        except ValueError:
            raise RuntimeError("prompt_batch is not valid JSON — open the "
                               "forge and save a batch to the node.")
        prompts = data.get("prompts") if isinstance(data, dict) else None
        if not isinstance(prompts, list) or not prompts:
            raise RuntimeError("The prompt batch is empty — open the forge, "
                               "generate prompts, and Save to node.")
        count = len(prompts)
        effective = int(index) % count
        return (str(prompts[effective]), effective, count)


NODE_CLASS_MAPPINGS = {
    "SCG_Prompt_Forge": SCG_Prompt_Forge,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SCG_Prompt_Forge": "SCG Prompt Forge",
}
