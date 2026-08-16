from html import escape

from app.domain.auction_state import AuctionState
from app.domain.notifications import NotificationDecision, NotificationKind
from app.domain.time import format_price, format_remaining


class NotificationRenderer:
    """Форматирует тексты уведомлений (HTML parse mode)."""

    @staticmethod
    def _link(url: str) -> str:
        return f'<a href="{escape(url)}">Открыть аукцион</a>'

    @staticmethod
    def _title(state: AuctionState, label: str | None = None) -> str:
        return escape(label or state.title or "Без названия")

    def render(self, decision: NotificationDecision, url: str, label: str | None = None) -> str:
        current = decision.current
        previous = decision.previous
        if current is None:
            return "Аукцион недоступен."

        title = self._title(current, label)
        if decision.kind == NotificationKind.T_30M:
            return self._header("🔔 До окончания аукциона 30 минут", title, current, url)
        if decision.kind == NotificationKind.T_15M:
            return self._header("🔔 До окончания 15 минут", title, current, url)
        if decision.kind == NotificationKind.T_5M:
            return self._header("⚠️ До окончания аукциона 5 минут", title, current, url)
        if decision.kind == NotificationKind.CLOSED:
            lines = ["🏁 Аукцион завершён", "", f"🎮 {title}"]
            if current.current_price is not None:
                lines.append(f"💴 Итоговая ставка: {format_price(current.current_price)}")
            if current.has_winner:
                lines.append("✅ Победитель определён")
            lines.append("")
            lines.append(self._link(url))
            return "\n".join(lines)
        if decision.kind == NotificationKind.EXTENSION:
            lines = ["⏰ Аукцион продлён", "", f"🎮 {title}"]
            if previous and previous.end_time and current.end_time:
                lines.append("")
                lines.append(f"Было: {format_remaining(previous.end_time)}")
                lines.append(f"Стало: {format_remaining(current.end_time)}")
            lines.append("")
            lines.append(self._link(url))
            return "\n".join(lines)
        # CHANGE
        lines = ["🔴 Изменение аукциона", "", f"🎮 {title}", ""]
        if previous is not None:
            if current.current_price is not None and previous.current_price != current.current_price:
                lines.append(
                    f"💴 Ставка: {format_price(previous.current_price)} → {format_price(current.current_price)}"
                )
            if current.bid_count is not None and previous.bid_count != current.bid_count:
                lines.append(f"👥 Ставок: {previous.bid_count} → {current.bid_count}")
            if current.end_time is not None and previous.end_time != current.end_time:
                lines.append(
                    f"⏰ До конца: {format_remaining(previous.end_time)} → "
                    f"{format_remaining(current.end_time)}"
                )
        lines.append("")
        lines.append(self._link(url))
        return "\n".join(lines)

    def render_added(self, state: AuctionState, url: str) -> str:
        lines = ["✅ Аукцион добавлен", "", f"🎮 {self._title(state)}"]
        if state.current_price is not None:
            lines.append(f"💴 Текущая ставка: {format_price(state.current_price)}")
        if state.bid_count is not None:
            lines.append(f"👥 Ставок: {state.bid_count}")
        if state.end_time is not None:
            lines.append(f"⏰ До конца: {format_remaining(state.end_time)}")
        lines.append("")
        lines.append(self._link(url))
        return "\n".join(lines)

    def _header(self, header: str, title: str, state: AuctionState, url: str) -> str:
        lines = [header, "", f"🎮 {title}"]
        if state.current_price is not None:
            lines.append(f"💴 Текущая ставка: {format_price(state.current_price)}")
        if state.bid_count is not None:
            lines.append(f"👥 Ставок: {state.bid_count}")
        if state.end_time is not None:
            lines.append(f"⏰ До конца: {format_remaining(state.end_time)}")
        lines.append("")
        lines.append(self._link(url))
        return "\n".join(lines)
