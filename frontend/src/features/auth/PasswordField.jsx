import { useState } from "react";

import { FormField } from "../../components/form-primitives";

export default function PasswordField({
  htmlFor,
  label,
  value,
  onChange,
  placeholder,
  autoComplete,
}) {
  const [visible, setVisible] = useState(false);

  return (
    <FormField htmlFor={htmlFor} label={label}>
      <div className="password-field">
        <input
          autoComplete={autoComplete}
          className="text-input text-input--with-toggle"
          id={htmlFor}
          onChange={onChange}
          placeholder={placeholder}
          type={visible ? "text" : "password"}
          value={value}
        />
        <button
          aria-label={`${visible ? "Hide" : "Show"} ${label.toLowerCase()}`}
          aria-pressed={visible}
          className="password-field__toggle"
          onClick={() => setVisible((current) => !current)}
          type="button"
        >
          {visible ? "Hide" : "Show"}
        </button>
      </div>
    </FormField>
  );
}
