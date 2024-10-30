/** Provide a reusable way to make API requests and show errors in a dialog.

This module exports the React `HTTPErrorProvider` to wrap your main application
and a React context `HTTPErrorContext` that contains the function `showError` to
display an error dialog.

See https://www.freecodecamp.org/news/how-to-use-react-context/ for a brief
overview of how React contexts work.
*/
import * as React from "react";
import { createContext } from "react";

import {
    Box,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Typography,
} from "@mui/material";

// The error context will provide access to a `showError` function. The child
// components can then access that function via `HTTPErrorContext` defined below.
export interface HTTPErrorContextType {
    showError: (err: HTTPErrorType) => void;
}

interface HTTPErrorType {
    status: number; // HTTP status code
    payload: string; // raw text payload before JSON decoding.
    url: URL;
    method: string;
}

// Define a handle to the context that client components can access.
export const HTTPErrorContext = createContext<HTTPErrorContextType>({
    showError: (_err: HTTPErrorType) => {
        console.log("default showError - you should not be seeing this");
    },
});

/**
 * A utility function to perform API fetch requests with error handling.
 *
 * @async
 * @function
 * @param {string} url - The endpoint URL to which the request is sent.
 * @param {Object} options - The configuration options for the fetch request (e.g., method, headers, body).
 * @throws {Object} Throws an error object containing the HTTP status and payload if the request fails.
 * @returns Resolves with the JSON response data for successful requests.
 *
 * @example
 * // Example usage:
 * try {
 *     const data = await fetchApi('/api/data', { method: 'GET' });
 *     console.log(data);
 * } catch (error) {
 *     console.error("Fetch failed:", error.status, error.payload);
 * }
 *
 * This function provides centralized error handling for HTTP requests, where a non-OK
 * response automatically raises an error with the status and response payload for improved
 * error management in calling components.
 */
interface FetchApiResponse<T = any> {
    data: T | null;
    err: HTTPErrorType | null;
}

export const fetchApi = async <T = any,>(
    url: string,
    options: any,
): Promise<FetchApiResponse<T>> => {
    try {
        const response = await fetch(url, options);

        if (!response.ok) {
            const errorData = await response.text();
            const err: HTTPErrorType = {
                status: response.status,
                payload: errorData,
                url: new URL(response.url),
                method: options.method,
            };
            return { data: null, err }; // Return error with data as null
        }

        if (options.method == "DELETE") {
            return { data: null, err: null };
        }
        const data = await response.json(); // Parse and return JSON payload
        return { data, err: null }; // Return data with no error
    } catch (error) {
        console.log(error);
        const err: HTTPErrorType = {
            status: 500, // Default to 500 for network or unexpected errors
            payload: (error as Error).message,
            url: new URL(url),
            method: options.method,
        };
        return { data: null, err: err }; // Return error with data as null
    }
};

// Convenience wrappers.
export const httpGet = async (url: string, options: any = {}) => {
    options = { ...options, method: "GET" };
    return await fetchApi(url, options);
};

export const httpPost = async (url: string, options: any = {}) => {
    // Method is *always* POST whereas the user is free override the content type.
    options = {
        headers: { "Content-Type": "application/json", ...options.headers },
        ...options,
        method: "POST",
    };
    return await fetchApi(url, options);
};

export const httpDelete = async (url: string, options: any = {}) => {
    options = { ...options, method: "DELETE" };
    return await fetchApi(url, options);
};

/**
 * Provides an HTTP error context for managing and displaying HTTP errors within the application.
 * Wraps the application components, offering a shared `showError` function for setting HTTP errors.
 * When an error is set, an error dialog is displayed, and users can clear the error to close the dialog.
 *
 *
 * @component
 * @example
 * ```tsx
 * <HTTPErrorProvider>
 *   <App />
 * </HTTPErrorProvider>
 * ```
 *
 * @context HTTPErrorContext - Exposes `showError` to set an HTTP error from any component within the provider.
 *
 * - `showError(status: number, payload: any)`: Function to trigger an error dialog with a status code and additional error data.
 */
export const HTTPErrorProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    // Convenience: default error value that is tantamount to no error.
    const NoError: HTTPErrorType = {
        status: 0,
        payload: "",
        url: new URL("http://nohost"),
        method: "GET",
    };

    const [error, setError] = React.useState<HTTPErrorType>(NoError);

    // This function is shared via the error context. The various components of this app
    // can access it via the React context to trigger the error dialog.
    const showError = (err: HTTPErrorType) => {
        setError(err);
    };

    const clearError = () => {
        setError(NoError);
    };

    return (
        <HTTPErrorContext.Provider value={{ showError }}>
            {/* Insert the error dialog whenever the error status is non-zero.*/}
            {error.status ? <HTTPErrorDialog httpError={error} onClose={clearError} /> : null}
            {children}
        </HTTPErrorContext.Provider>
    );
};

/**
 * A modal dialog component to display HTTP error details in a readable format.
 *
 * @component
 * @param httpError - The HTTP error details to display, including status and payload.
 * @param onClose - Callback function triggered when the dialog is closed.
 *
 * @returns A dialog box showing the HTTP error status and formatted payload details.
 *
 * @example
 * // Example usage:
 * <HTTPErrorDialog
 *     httpError={{ status: 404, payload: { message: "Not found" }}}
 *     onClose={handleClose}
 * />
 *
 * This component is useful for presenting HTTP error information in a consistent,
 * user-friendly way, allowing for easy debugging and error resolution.
 */
const HTTPErrorDialog = ({
    httpError,
    onClose,
}: {
    httpError: HTTPErrorType;
    onClose: () => void;
}) => {
    // Decode `text` as JSON if possible or return it verbatim if not.
    const parsePayload = (text: string) => {
        try {
            const json = JSON.parse(text);
            return JSON.stringify(json, null, 2);
        } catch (e) {
            return text;
        }
    };

    return (
        <Dialog open={Boolean(httpError)} onClose={onClose}>
            <DialogTitle>HTTP Error {httpError.status}</DialogTitle>
            <DialogContent>
                <Typography variant="body1" gutterBottom>
                    {httpError.method} {httpError.url.host}
                    {httpError.url.pathname}
                </Typography>

                <Box
                    sx={{
                        maxWidth: "100%", // Ensures it fits within the dialog width
                        overflowX: "auto", // Enables horizontal scroll
                        backgroundColor: "#f5f5f5",
                        padding: 1,
                        borderRadius: 1,
                    }}
                >
                    <Typography
                        component="pre"
                        variant="body2"
                        style={{ margin: 0, fontFamily: "monospace" }}
                    >
                        {parsePayload(httpError.payload)}
                    </Typography>
                </Box>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} color="primary">
                    Close
                </Button>
            </DialogActions>
        </Dialog>
    );
};
