# Auto-activate this project's virtual environment when entering the folder.

typeset -g PHY_IA_MARKER_PROJECT_ROOT="${${(%):-%N}:A:h}"
typeset -g PHY_IA_MARKER_PROJECT_VENV="${PHY_IA_MARKER_PROJECT_ROOT}/.venv"

_phy_ia_marker_project_auto_venv() {
  local root="${PHY_IA_MARKER_PROJECT_ROOT:A}"
  local current="${PWD:A}"
  local project_venv="${PHY_IA_MARKER_PROJECT_VENV:A}"
  local active_venv=""
  local activate_script="${project_venv}/bin/activate"

  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    active_venv="${VIRTUAL_ENV:A}"
  fi

  if [[ "${current}" == "${root}" || "${current}" == "${root}/"* ]]; then
    if [[ "${active_venv}" != "${project_venv}" && -f "${activate_script}" ]]; then
      if [[ -n "${VIRTUAL_ENV:-}" ]] && typeset -f deactivate >/dev/null 2>&1; then
        deactivate >/dev/null 2>&1 || true
      fi

      source "${activate_script}"
      export PHY_IA_MARKER_PROJECT_AUTO_VENV_ACTIVE=1
    fi
  elif [[ -n "${PHY_IA_MARKER_PROJECT_AUTO_VENV_ACTIVE:-}" && "${active_venv}" == "${project_venv}" ]] && typeset -f deactivate >/dev/null 2>&1; then
    deactivate >/dev/null 2>&1 || true
    unset PHY_IA_MARKER_PROJECT_AUTO_VENV_ACTIVE
  fi
}

autoload -U add-zsh-hook
add-zsh-hook chpwd _phy_ia_marker_project_auto_venv
_phy_ia_marker_project_auto_venv
