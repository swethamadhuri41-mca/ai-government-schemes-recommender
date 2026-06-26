// ---------------------------------------------------------------
// AI Personalized Government Schemes and Jobs Eligibility Recommender
// Lightweight client-side validation. This is a UX convenience layer
// only - the server in app.py performs the authoritative validation,
// so the app still works correctly even if JavaScript is disabled.
// ---------------------------------------------------------------

document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("eligibility-form");
  if (!form) {
    return; // We're on a page without the form (e.g. the results page).
  }

  var submitBtn = document.getElementById("submit-btn");

  form.addEventListener("submit", function (event) {
    var isValid = true;
    var firstInvalidField = null;

    // Clear any previous inline error messages before re-validating.
    form.querySelectorAll(".field-error").forEach(function (el) {
      el.remove();
    });

    var requiredFields = form.querySelectorAll("[required]");
    requiredFields.forEach(function (field) {
      var value = (field.value || "").trim();
      var fieldIsValid = value !== "";

      // Extra check: age must be a sensible whole number between 1 and 100.
      if (field.id === "age" && value !== "") {
        var ageNum = Number(value);
        if (!Number.isInteger(ageNum) || ageNum < 1 || ageNum > 100) {
          fieldIsValid = false;
        }
      }

      // Extra check: annual income must be a non-negative number.
      if (field.id === "annual_income" && value !== "") {
        var incomeNum = Number(value);
        if (Number.isNaN(incomeNum) || incomeNum < 0) {
          fieldIsValid = false;
        }
      }

      if (!fieldIsValid) {
        isValid = false;
        showFieldError(field, "This field needs a valid value.");
        if (!firstInvalidField) {
          firstInvalidField = field;
        }
      }
    });

    if (!isValid) {
      event.preventDefault();
      if (firstInvalidField) {
        firstInvalidField.focus();
      }
      return;
    }

    // Prevent double-submission while the server processes the request.
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "Checking Eligibility...";
    }
  });

  function showFieldError(field, message) {
    var error = document.createElement("div");
    error.className = "field-error";
    error.textContent = message;
    field.insertAdjacentElement("afterend", error);
  }
});
