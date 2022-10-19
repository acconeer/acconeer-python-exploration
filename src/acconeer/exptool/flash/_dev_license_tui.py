# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import List

from textual import events
from textual.app import App
from textual.geometry import Spacing
from textual.widgets import Button, ButtonPressed, Header, ScrollView

from ._dev_license import DevLicense


class DevLicenseTuiDialog(App):

    # The reason for this class variable is that the textual app is started
    # using the class method App#run, which in turn instantiate the subclass
    # DevLicenseTuiDialog. Because of this we don't (easily) get a handle to
    # the textual app instance.
    accepted = False

    def __init__(
        self,
        license: DevLicense,
        screen: bool = True,
        driver_class=None,
        log: str = "",
        log_verbosity: int = 1,
        title: str = "",
    ):

        super().__init__(screen, driver_class, log, log_verbosity, title)

        self.license = license

        self.tab_order: List[Button] = []
        self.tab_index = -1

    @classmethod
    def get_accept(cls) -> bool:
        return cls.accepted

    async def on_load(self) -> None:
        await self.bind("q", "quit", "Quit")

    async def on_mount(self) -> None:
        self.title = self.license.get_header()
        header = Header(tall=False)
        await self.view.dock(header, edge="top")

        text_view = ScrollView(contents=self._get_license_text(), auto_width=False)

        user_consent_label = Button(
            label="To fetch the latest image file you must accept the "
            "terms and conditions stated by the license above!",
            style="bold white on rgb(50,57,50)",
        )

        user_consent_label.margin = Spacing(1, 0, 0, 0)

        self.accept_button = Button(
            label="Accept", name="accept", style="bold white on rgb(96,96,104)"
        )
        self.accept_button.margin = Spacing(1, 1, 1, 1)
        self.accept_button.border = "normal"

        self.reject_button = Button(
            label="Reject", name="reject", style="bold white on rgb(96,96,104)"
        )
        self.reject_button.margin = Spacing(1, 1, 1, 1)
        self.reject_button.border = "normal"

        self.tab_order.append(self.accept_button)
        self.tab_order.append(self.reject_button)

        await self.view.dock(text_view, size=20)
        await self.view.dock(user_consent_label, size=4)

        button_grid = await self.view.dock_grid(size=5)
        button_grid.add_column("col", repeat=2)
        button_grid.add_row("row", repeat=1)
        button_grid.set_align("strech", "center")
        button_grid.set_gap(1, 1)

        button_grid.add_widget(self.accept_button)
        button_grid.add_widget(self.reject_button)

    def _get_license_text(self) -> str:
        license_header = [self.license.get_subheader(), "\n\n"]
        paragraphs = "\n\n".join(self.license.get_content())
        return "".join([*license_header, *paragraphs])

    async def handle_button_pressed(self, message: ButtonPressed) -> None:
        assert isinstance(message.sender, Button)
        await self.save_user_consent_and_exit(message.sender.name)

    async def save_user_consent_and_exit(self, button_name: str) -> None:
        if button_name == "accept":
            DevLicenseTuiDialog.accepted = True
            await self.close_messages()
        elif button_name == "reject":
            DevLicenseTuiDialog.accepted = False
            await self.close_messages()

    async def on_key(self, event: events.Key) -> None:
        if event.key == "ctrl+i":
            if self.tab_index == -1:
                self.tab_index = 0
            else:
                self.tab_index = (self.tab_index + 1) % len(self.tab_order)

            for index, button in enumerate(self.tab_order):
                if index != self.tab_index:
                    button.border = "normal"
                    button.render_styled()

            selected_button = self.tab_order[self.tab_index]
            selected_button.border = "bold"
            selected_button.render_styled()

        elif event.key == "enter":
            if self.tab_index != -1:
                selected_button = self.tab_order[self.tab_index]
                await self.save_user_consent_and_exit(selected_button.name)
