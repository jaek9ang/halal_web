import { useEffect } from "react";

function getNearestScrollableParent(element) {
  let parent = element?.parentElement;

  while (parent) {
    const style = window.getComputedStyle(parent);
    const canScrollY =
      ["auto", "scroll"].includes(style.overflowY) &&
      parent.scrollHeight > parent.clientHeight;

    if (canScrollY) return parent;

    parent = parent.parentElement;
  }

  return null;
}

function useAutoScrollActiveRows() {
  useEffect(() => {
    let rafId = null;

    function scrollActiveIntoView() {
      if (rafId) cancelAnimationFrame(rafId);

      rafId = requestAnimationFrame(() => {
        const activeElements = document.querySelectorAll(
          [
            ".active",
            ".is-selected",
            "[aria-selected='true']",
          ].join(",")
        );

        activeElements.forEach((element) => {
          const scroller = getNearestScrollableParent(element);

          if (!scroller) return;

          const elementRect = element.getBoundingClientRect();
          const scrollerRect = scroller.getBoundingClientRect();

          const isAbove = elementRect.top < scrollerRect.top;
          const isBelow = elementRect.bottom > scrollerRect.bottom;

          if (isAbove || isBelow) {
            element.scrollIntoView({
              block: "nearest",
              inline: "nearest",
            });
          }
        });
      });
    }

    const observer = new MutationObserver(scrollActiveIntoView);

    observer.observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "aria-selected"],
    });

    window.addEventListener("keydown", scrollActiveIntoView, true);

    return () => {
      observer.disconnect();
      window.removeEventListener("keydown", scrollActiveIntoView, true);

      if (rafId) cancelAnimationFrame(rafId);
    };
  }, []);
}

export default useAutoScrollActiveRows;
