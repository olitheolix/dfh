declare module "js-cookie" {
    interface CookieAttributes {
        expires?: number | Date;
        path?: string;
        domain?: string;
        secure?: boolean;
        sameSite?: "lax" | "strict" | "none";
    }

    function set(
        name: string,
        value: string | object,
        options?: CookieAttributes,
    ): string;
    function get(name: string): string | undefined;
    function remove(name: string, options?: CookieAttributes): void;
    function getJSON(name: string): any | undefined;

    export { set, get, remove, getJSON };
}
