"""Extract stage: model call (text or vision) -> menu JSON.

``MealChat`` is ``locations/.shared/DefaultMealChat.py`` moved into the runner
and simplified, not redesigned (plan section 3.4):

- Constructor parameters come from the validated location config instead of the
  ``config.py`` / ``prompt_overrides`` pair.
- The ``{MC_TODAY}`` / ``{MC_WEEKSTART}`` templating, weekend-rolls-to-next-week
  logic, and ``add_current_date`` / ``add_current_weekdays`` behavior are
  preserved verbatim (the prompt regression tests depend on it).
- The OpenAI-compatible provider switch (``openai`` vs ``google`` base URL +
  env var) is preserved; adding providers is out of scope.
- The ``sed -n '/^\\s*{$/,$p'`` JSON-carving done in workflow shell is the
  tested :func:`extract_json_object` function below.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from datetime import datetime, timedelta
from pathlib import Path


class ExtractError(Exception):
    pass


def extract_json_object(text: str) -> str:
    """Carve the outermost JSON object out of a model response.

    Replaces the workflow shell's ``sed -n '/^\\s*{$/,$p'`` / awk carving.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ExtractError("no JSON object found in model response")
    return text[start:end + 1]


class MealChat:
    """DefaultMealChat absorbed into the runner (plan section 3.4)."""

    def __init__(self,
                 user_message=None,
                 user_message_file="chatgpt_user.txt",
                 user_message_prefix="",
                 user_image_file="image_input",
                 date_override=None,
                 output_prefix="chatgpt",
                 max_tokens=1000,
                 system_prompt="",
                 json_schema="",
                 add_current_date=True,
                 add_current_weekdays=True,
                 model_provider="openai",
                 vision_model="gpt-4o-2024-08-06",
                 text_model="gpt-4o-mini",
                 model_override=None,
                 base_url=None,
                 api_key=None,
                 run_dir="."):
        self.output_prefix = output_prefix
        self.system_prompt = system_prompt
        self.json_schema = json_schema
        self.add_current_date = add_current_date
        self.add_current_weekdays = add_current_weekdays
        self.model_provider = model_provider
        self.vision_model = vision_model
        self.text_model = text_model
        # explicit override for both text and vision calls (testing/proxies)
        self.model_override = model_override
        self.max_tokens = int(os.environ.get("PIPELINE_MAX_TOKENS", max_tokens))
        self.run_dir = Path(run_dir)
        self._base_url = base_url
        self._api_key = api_key

        if date_override is not None:
            today = datetime.strptime(date_override, "%Y-%m-%d")
        else:
            today = datetime.today()
        week_start = today - timedelta(days=today.weekday())
        # if on weekend assume we are running for next week
        if today.weekday() > 4:
            week_start = week_start + timedelta(days=7)
        self.week_start = week_start

        self.user_image_file = user_image_file
        self.user_message_prefix = user_message_prefix.format(
            MC_TODAY=self.week_start.strftime("%Y-%m-%d"),
            MC_WEEKSTART=self.week_start.strftime("%G-W%V"),
        )
        if user_message is None:
            with open(self.run_dir / user_message_file, "r", encoding="utf-8") as fh:
                self.user_message = fh.read()
        else:
            self.user_message = user_message

    # -- provider configuration -------------------------------------------------

    def model_provider_config(self) -> dict:
        """OpenAI-compatible provider switch (openai | google), preserved.

        ``PIPELINE_MODEL_BASE_URL`` / ``PIPELINE_MODEL_API_KEY`` /
        ``PIPELINE_MODEL`` environment variables override the endpoint and
        model for local testing against OpenAI-compatible proxies.
        """
        return {
            "base_url": (
                self._base_url
                or os.environ.get("PIPELINE_MODEL_BASE_URL")
                or self._default_base_url()
            ),
            "api_key": (
                self._api_key
                or os.environ.get("PIPELINE_MODEL_API_KEY")
                or self._default_api_key()
            ),
        }

    def _effective_model(self, configured: str) -> str:
        return self.model_override or os.environ.get("PIPELINE_MODEL") or configured

    def _default_base_url(self) -> str:
        if self.model_provider == "google":
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        return "https://api.openai.com/v1"

    def _default_api_key(self) -> str | None:
        if self.model_provider == "google":
            return os.environ.get("GEMINI_API_KEY")
        return os.environ.get("CHAT_API_KEY")

    # -- templating (preserved verbatim) ---------------------------------------

    def weekdays_from_date(self, date_string: str) -> str:
        week_days = []
        date = datetime.strptime(date_string, "%Y-%m-%d")
        week_start = date - timedelta(days=date.weekday())
        for i in range(7):
            weekday = (week_start + timedelta(days=i)).strftime("%A")
            day = (week_start + timedelta(days=i)).strftime("%Y-%m-%d")
            week_days.append(f"{weekday}({day})")
        return f"{', '.join(week_days)}"

    def default_substitutions(self) -> dict:
        return {
            "MC_JSON_SCHEMA": self.json_schema,
            "MC_TODAY": self.week_start.strftime("%Y-%m-%d"),
            "MC_WEEKSTART": self.week_start.strftime("%G-W%V"),
        }

    def prompt_addon_messages(self) -> list[dict]:
        gpt_messages = []
        weekdays_explicit = ""
        if self.add_current_weekdays:
            weekdays_explicit = (
                " containing the days "
                + self.weekdays_from_date(self.week_start.strftime("%Y-%m-%d"))
            )
        if self.add_current_date:
            gpt_messages.append({
                "role": "user",
                "content": (
                    "When you determine the calendar period from the input take "
                    "your time to conclude if the period is reasonable as today "
                    "is \"Monday\" {MC_TODAY} and calendar week "
                    "{MC_WEEKSTART}{weekdays_explicit}. You may need to "
                    "reconsider if you determine a calendar week from the very "
                    "past. Otherwise the period most likely will be for the "
                    "current week or a few weeks in the future from today."
                ).format(
                    **self.default_substitutions(),
                    weekdays_explicit=weekdays_explicit,
                ),
            })
        return gpt_messages

    # -- helpers ----------------------------------------------------------------

    def encode_image(self, image_path: Path) -> str:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")
            mime_type, _ = mimetypes.guess_type(str(image_path))
            return f"data:{mime_type};base64,{base64_image}"

    def _client(self):
        from openai import OpenAI

        return OpenAI(**self.model_provider_config())

    def _base_messages(self) -> list[dict]:
        system_prompt = self.system_prompt.format(**self.default_substitutions())
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.prompt_addon_messages())
        return messages

    def _write_output(self, chat_completion) -> dict:
        prefix = self.output_prefix or (
            f"{self.model_provider}_{self.vision_model}"
        )
        usage = chat_completion.usage
        with open(self.run_dir / f"{prefix}_usage.json", "w", encoding="utf-8") as fh:
            json.dump(
                usage.model_dump() if hasattr(usage, "model_dump") else usage.to_dict(),
                fh, indent=4, sort_keys=True,
            )
        content = chat_completion.choices[0].message.content
        raw = extract_json_object(content)
        with open(self.run_dir / f"{prefix}.json", "w", encoding="utf-8") as fh:
            fh.write(raw)
        return json.loads(raw)

    # -- public processing API ---------------------------------------------------

    def process_image(self) -> dict:
        """Vision extraction; returns the parsed menu JSON."""
        messages = self._base_messages()
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": self.user_message_prefix + self.user_message,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self.encode_image(self.run_dir / self.user_image_file)
                    },
                },
            ],
        })
        chat_completion = self._client().chat.completions.create(
            model=self._effective_model(self.vision_model),
            messages=messages,
            max_tokens=self.max_tokens,
        )
        return self._write_output(chat_completion)

    def process_text(self) -> dict:
        """Text extraction; returns the parsed menu JSON."""
        messages = self._base_messages()
        messages.append({
            "role": "user",
            "content": self.user_message_prefix + self.user_message,
        })
        chat_completion = self._client().chat.completions.create(
            model=self._effective_model(self.text_model),
            messages=messages,
            response_format={"type": "text"},
            temperature=0.1,
            seed=1,
            max_tokens=self.max_tokens,
        )
        return self._write_output(chat_completion)


def meal_chat_from_config(extract_cfg: dict, prompts: dict, location_dir: Path,
                          run_dir: str | Path = ".", date_override=None,
                          output_prefix="chatgpt", user_image_file=None,
                          base_url=None, api_key=None, model_override=None) -> MealChat:
    """Build a MealChat from a validated extract config block."""
    model = extract_cfg.get("model") or {}
    user_message = extract_cfg.get("prompt")
    prompt_file = extract_cfg.get("prompt_file")
    if user_message is None and prompt_file:
        with open(location_dir / prompt_file, "r", encoding="utf-8") as fh:
            user_message = fh.read()
    return MealChat(
        user_message=user_message,
        user_message_file=extract_cfg.get("input_file", "chatgpt_user.txt"),
        user_message_prefix=extract_cfg.get("prompt_prefix", ""),
        user_image_file=user_image_file or extract_cfg.get("input_file", "image_input"),
        date_override=date_override,
        output_prefix=output_prefix,
        max_tokens=extract_cfg.get("max_tokens", 1000),
        system_prompt=prompts.get("system_prompt", ""),
        json_schema=prompts.get("json_schema", ""),
        add_current_date=extract_cfg.get("add_current_date", True),
        add_current_weekdays=extract_cfg.get("add_current_weekdays", True),
        model_provider=model.get("provider", "openai"),
        vision_model=model.get("vision_model", "gpt-4o-2024-08-06"),
        text_model=model.get("text_model", "gpt-4o-mini"),
        model_override=model_override,
        base_url=base_url,
        api_key=api_key,
        run_dir=run_dir,
    )


def extract(run_dir: str | Path, extract_cfg: dict, prompts: dict,
            location_dir: Path, base_url=None, api_key=None,
            output_prefix="chatgpt", model_override=None) -> dict:
    """Run the extraction for one prepared input; returns the menu JSON."""
    chat = meal_chat_from_config(
        extract_cfg, prompts, Path(location_dir), run_dir=run_dir,
        output_prefix=output_prefix, base_url=base_url, api_key=api_key,
        model_override=model_override,
    )
    if extract_cfg.get("type") == "vision":
        return chat.process_image()
    return chat.process_text()
