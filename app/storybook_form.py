"""Settings for the standalone public storybook enquiry form."""
import hashlib
from datetime import date
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .models import SystemSetting

KEY = "public_storybook_form"
THEMES = {
    "wedding": "Wedding Storybook",
    "christmas_wedding": "Christmas Wedding",
    "christmas": "Christmas Adventure",
    "holiday": "Holiday Adventure",
}
ThemeKey = Annotated[str, StringConstraints(pattern=r"^(wedding|christmas_wedding|christmas|holiday|story_[a-f0-9]{32})$")]
QuestionKey = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\x00-\x1f\x7f]+$")]
Copy = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class FormStory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: ThemeKey
    label: Name
    enabled: bool = True


class FormQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: QuestionKey
    label: Name
    kind: Literal["text", "paragraph", "date"] = "text"
    story: ThemeKey | None = None
    required: bool = False


class StorybookForm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Name = "Order a personalised storybook"
    intro: Copy = ("Choose a wedding keepsake, a Christmas story or a holiday adventure. Anyone can request a book, "
                   "including as a gift.\n\nTell me who the book is for. I’ll reply by email to confirm the design, "
                   "price and delivery timing.")
    button: Name = "Send storybook order request"
    thanks: Copy = "Thanks, I’ve got your storybook request. I’ll reply by email to confirm the details, delivery timing and how to pay."
    stories: list[FormStory] = Field(default_factory=lambda: [FormStory(id=k, label=v) for k, v in THEMES.items()],
                                     min_length=1, max_length=50)
    questions: list[FormQuestion] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def check_options(self):
        keys = {story.id for story in self.stories}
        if len(keys) != len(self.stories) or len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Each story and question must have its own identifier.")
        labels = [story.label.casefold() for story in self.stories if story.enabled]
        if not labels or len(set(labels)) != len(labels):
            raise ValueError("Keep at least one visible story and give each visible story a different name.")
        if any(q.story is not None and q.story not in keys for q in self.questions):
            raise ValueError("Choose an existing story for each extra question, or show it for all stories.")
        return self

    def revision(self):
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class SavedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Name
    answer: Copy


def get_form(db):
    row = db.get(SystemSetting, KEY)
    return StorybookForm.model_validate(row.value) if row else StorybookForm()


def collect_answers(form, theme, answers):
    relevant = {question.id: question for question in form.questions if question.story in (None, theme)}
    if answers.keys() - relevant.keys():
        raise HTTPException(422, "Some questions have changed. Reopen the order form and try again.")
    saved = []
    for key, question in relevant.items():
        answer = answers.get(key, "").strip()
        if not answer:
            if question.required:
                raise HTTPException(422, f"Please answer: {question.label}")
            continue
        if question.kind == "text" and (len(answer) > 160 or "\n" in answer or "\r" in answer):
            raise HTTPException(422, f"Please use one line of up to 160 characters for: {question.label}")
        if question.kind == "date":
            try:
                valid = date.fromisoformat(answer).isoformat() == answer
            except ValueError:
                valid = False
            if not valid:
                raise HTTPException(422, f"Please enter a date for: {question.label}")
        saved.append(SavedAnswer(question=question.label, answer=answer))
    return saved
