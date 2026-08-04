(function () {
  let mapsPromise;

  async function loadMaps() {
    if (window.google?.maps?.importLibrary) return window.google.maps;
    if (mapsPromise) return mapsPromise;
    mapsPromise = (async () => {
      const response = await fetch("/api/public/config");
      const config = await response.json();
      if (!config.google_maps_enabled || !config.google_maps_api_key) {
        throw new Error("Google venue search is not configured");
      }
      await new Promise((resolve, reject) => {
        const callback = `wbmMapsReady${Date.now()}`;
        window[callback] = () => {
          delete window[callback];
          resolve();
        };
        const script = document.createElement("script");
        script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(config.google_maps_api_key)}&loading=async&libraries=places&v=weekly&callback=${callback}`;
        script.async = true;
        script.onerror = () => {
          delete window[callback];
          reject(new Error("Google venue search could not load"));
        };
        document.head.appendChild(script);
      });
      return window.google.maps;
    })();
    return mapsPromise;
  }

  function element(value) {
    return typeof value === "string" ? document.querySelector(value) : value;
  }

  function setValue(target, value) {
    const node = element(target);
    if (node) node.value = value ?? "";
  }

  function getValue(target) {
    return element(target)?.value || "";
  }

  function mapsUrl(placeId, lat, lng, fallback) {
    if (placeId) {
      return `https://www.google.com/maps/dir/?api=1&destination_place_id=${encodeURIComponent(placeId)}&destination=${encodeURIComponent(fallback || "Wedding venue")}`;
    }
    if (lat !== "" && lng !== "" && lat != null && lng != null) {
      return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${lat},${lng}`)}`;
    }
    return fallback ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(fallback)}` : "";
  }

  function updateSummary(options) {
    const summary = element(options.summary);
    if (!summary) return;
    const name = getValue(options.name);
    const address = getValue(options.address);
    const url = mapsUrl(getValue(options.placeId), getValue(options.lat), getValue(options.lng), address || name);
    if (!name) {
      summary.innerHTML = "<span>No venue selected yet</span>";
      summary.classList.remove("has-venue");
      return;
    }
    const safe = value => String(value || "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
    summary.classList.add("has-venue");
    summary.innerHTML = `<span><strong>${safe(name)}</strong>${address && address !== name ? `<small>${safe(address)}</small>` : ""}</span>${url ? `<a href="${safe(url)}" target="_blank" rel="noopener">Directions ↗</a>` : ""}`;
  }

  function showManual(options, message = "") {
    const manual = element(options.manual);
    const host = element(options.host);
    const toggle = element(options.manualToggle);
    if (manual) {
      manual.hidden = false;
      manual.required = Boolean(options.required);
      if (!manual.value) manual.value = getValue(options.name);
      manual.oninput = () => {
        setValue(options.name, manual.value.trim());
        setValue(options.address, manual.value.trim());
        setValue(options.placeId, "");
        setValue(options.lat, "");
        setValue(options.lng, "");
        updateSummary(options);
      };
    }
    if (host && message) host.innerHTML = `<small class="venue-help">${message}</small>`;
    if (toggle) toggle.textContent = "Use venue search instead";
  }

  async function attach(options) {
    const host = element(options.host);
    if (!host) return;
    const manual = element(options.manual);
    const toggle = element(options.manualToggle);
    updateSummary(options);
    if (manual) manual.hidden = true;
    if (toggle) {
      toggle.type = "button";
      toggle.onclick = () => {
        if (manual?.hidden) showManual(options);
        else {
          manual.hidden = true;
          manual.required = false;
          toggle.textContent = "Can't find it? Enter the venue manually";
        }
      };
    }
    try {
      await loadMaps();
      const {PlaceAutocompleteElement} = await google.maps.importLibrary("places");
      const picker = new PlaceAutocompleteElement();
      picker.placeholder = options.placeholder || "Start typing the wedding venue";
      picker.includedRegionCodes = ["gb"];
      picker.setAttribute("aria-label", options.placeholder || "Search for a wedding venue");
      host.replaceChildren(picker);

      picker.addEventListener("gmp-error", () => {
        console.error("Google Places autocomplete returned an error");
        showManual(options, "Google venue search returned an error - please enter the venue manually.");
      });

      picker.addEventListener("gmp-select", async ({placePrediction}) => {
        try {
          const place = placePrediction.toPlace();
          await place.fetchFields({fields: ["id", "displayName", "formattedAddress", "location"]});
          const name = place.displayName || place.formattedAddress || "";
          const address = place.formattedAddress || name;
          setValue(options.name, name);
          setValue(options.address, address);
          setValue(options.placeId, place.id || "");
          setValue(options.lat, place.location?.lat?.() ?? "");
          setValue(options.lng, place.location?.lng?.() ?? "");
          if (manual) {
            manual.value = name;
            manual.hidden = true;
            manual.required = false;
          }
          updateSummary(options);
          options.onSelect?.({
            name,
            address,
            placeId: place.id || "",
            lat: place.location?.lat?.() ?? null,
            lng: place.location?.lng?.() ?? null
          });
        } catch (error) {
          console.error("Unable to load selected Google venue", error);
          showManual(options, "The selected venue could not be loaded - please enter it manually.");
        }
      });
    } catch (error) {
      console.error("Unable to start Google venue search", error);
      showManual(options, "Venue search is unavailable at the moment - please enter it manually.");
    }
  }

  window.WBMVenues = {attach, mapsUrl};
})();
