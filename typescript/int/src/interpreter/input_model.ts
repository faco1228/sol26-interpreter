/**
 * This module defines the data models for representing SOL-XML programs in memory,
 * using TypeScript interfaces and explicit XML validation logic.
 *
 * IPP: You should not need to modify this file. If you find it necessary to modify it,
 *      consult your intentions on the project forum first.
 *
 * Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
 */

import { XMLParser, XMLValidator } from "fast-xml-parser";

// --- Leaf nodes ---

interface OrderedElementXmlModel {
  order: number;
}

export interface Var {
  /** <var name="..."/> */
  name: string;
}

export interface Literal {
  /** <literal class="Integer|String|Nil|True|False|class" value="..."/> */
  class_id: string;
  value: string;
}

export interface Parameter extends OrderedElementXmlModel {
  /** <parameter name="..." order="..."/> */
  name: string;
}

export interface Arg extends OrderedElementXmlModel {
  /** <arg order="..."><expr>...</expr></arg> */
  expr: Expr;
}

// --- Helpers ---

type XmlNode = Record<string, unknown>;

function toXmlNode(value: unknown, path: string): XmlNode {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ModelValidationError(`Expected XML object at ${path}.`);
  }
  return value as XmlNode;
}

function getRequiredAttribute(node: XmlNode, attributeName: string, path: string): string {
  const key = `@_${attributeName}`;
  const rawValue = node[key];
  if (typeof rawValue !== "string") {
    throw new ModelValidationError(`Missing required attribute '${attributeName}' at ${path}.`);
  }
  return rawValue;
}

function getOptionalAttribute(node: XmlNode, attributeName: string): string | null {
  const key = `@_${attributeName}`;
  const rawValue = node[key];
  if (rawValue === undefined) {
    return null;
  }
  if (typeof rawValue !== "string") {
    throw new ModelValidationError(`Attribute '${attributeName}' must be a string.`);
  }
  return rawValue;
}

function parseRequiredIntAttribute(node: XmlNode, attributeName: string, path: string): number {
  const rawValue = getRequiredAttribute(node, attributeName, path);
  const numberValue = Number(rawValue);
  if (!Number.isInteger(numberValue)) {
    throw new ModelValidationError(`Attribute '${attributeName}' at ${path} must be an integer.`);
  }
  return numberValue;
}

function getChildArray(node: XmlNode, tagName: string): unknown[] {
  const rawValue = node[tagName];
  if (rawValue === undefined) {
    return [];
  }
  if (Array.isArray(rawValue)) {
    return rawValue;
  }
  return [rawValue];
}

function getRequiredSingleChild(node: XmlNode, tagName: string, path: string): unknown {
  const children = getChildArray(node, tagName);
  if (children.length !== 1) {
    throw new ModelValidationError(`Expected exactly one <${tagName}> child at ${path}.`);
  }
  return children[0];
}

function sortByOrder<T extends OrderedElementXmlModel>(items: T[]): T[] {
  /** Sorts list of elements that carry an `order` attribute. */
  return [...items].sort((a, b) => a.order - b.order);
}

// --- Expression and statements ---

export interface Expr {
  /**
   * <expr> contains exactly one child, one of:
   *   - <literal .../>
   *   - <var .../>
   *   - <block ...>...</block>
   *   - <send ...>...</send>
   */
  literal: Literal | null;
  var: Var | null;
  block: Block | null;
  send: Send | null;
}

export interface Send {
  /**
   * <send selector="...">
   *   <expr>...</expr>
   *   <arg order="1"><expr>...</expr></arg>
   *   ...
   * </send>
   */
  selector: string;
  receiver: Expr;
  args: Arg[];
}

export interface Assign extends OrderedElementXmlModel {
  /**
   * <assign order="...">
   *   <var name="..."/>
   *   <expr>...</expr>
   * </assign>
   */
  target: Var;
  expr: Expr;
}

export interface Block {
  /**
   * <block arity="...">
   *   <parameter name="..." order="..."/>
   *   ...
   *   <assign order="...">...</assign>
   *   ...
   * </block>
   */
  arity: number;
  parameters: Parameter[];
  assigns: Assign[];
}

// --- Program structure ---

export interface Method {
  /**
   * <method selector="...">
   *   <block arity="...">...</block>
   * </method>
   */
  selector: string;
  block: Block;
}

export interface ClassDef {
  /**
   * <class name="..." parent="...">
   *   <method selector="...">...</method>
   *   ...
   * </class>
   */
  name: string;
  parent: string;
  methods: Method[];
}

export interface Program {
  /**
   * <program language="..." description="...">
   *   <class ...>...</class>
   *   ...
   * </program>
   */
  language: string;
  description: string | null;
  classes: ClassDef[];
}

function parseVar(rawNode: unknown, path: string): Var {
  const node = toXmlNode(rawNode, path);
  return {
    name: getRequiredAttribute(node, "name", path),
  };
}

function parseLiteral(rawNode: unknown, path: string): Literal {
  const node = toXmlNode(rawNode, path);
  return {
    class_id: getRequiredAttribute(node, "class", path),
    value: getRequiredAttribute(node, "value", path),
  };
}

function parseParameter(rawNode: unknown, path: string): Parameter {
  const node = toXmlNode(rawNode, path);
  return {
    name: getRequiredAttribute(node, "name", path),
    order: parseRequiredIntAttribute(node, "order", path),
  };
}

function parseArg(rawNode: unknown, path: string): Arg {
  const node = toXmlNode(rawNode, path);
  const exprNode = getRequiredSingleChild(node, "expr", path);
  return {
    order: parseRequiredIntAttribute(node, "order", path),
    expr: parseExpr(exprNode, `${path}/expr`),
  };
}

function parseExpr(rawNode: unknown, path: string): Expr {
  const node = toXmlNode(rawNode, path);

  const hasLiteral = node["literal"] !== undefined;
  const hasVar = node["var"] !== undefined;
  const hasBlock = node["block"] !== undefined;
  const hasSend = node["send"] !== undefined;

  const present = Number(hasLiteral) + Number(hasVar) + Number(hasBlock) + Number(hasSend);
  if (present !== 1) {
    throw new ModelValidationError("<expr> must contain exactly one of: literal|var|block|send");
  }

  return {
    literal: hasLiteral ? parseLiteral(node["literal"], `${path}/literal`) : null,
    var: hasVar ? parseVar(node["var"], `${path}/var`) : null,
    block: hasBlock ? parseBlock(node["block"], `${path}/block`) : null,
    send: hasSend ? parseSend(node["send"], `${path}/send`) : null,
  };
}

function parseSend(rawNode: unknown, path: string): Send {
  const node = toXmlNode(rawNode, path);
  const rawArgs = getChildArray(node, "arg");

  return {
    selector: getRequiredAttribute(node, "selector", path),
    receiver: parseExpr(getRequiredSingleChild(node, "expr", path), `${path}/expr`),
    args: sortByOrder(
      rawArgs.map((item, index) => parseArg(item, `${path}/arg[${String(index)}]`))
    ),
  };
}

function parseAssign(rawNode: unknown, path: string): Assign {
  const node = toXmlNode(rawNode, path);

  return {
    order: parseRequiredIntAttribute(node, "order", path),
    target: parseVar(getRequiredSingleChild(node, "var", path), `${path}/var`),
    expr: parseExpr(getRequiredSingleChild(node, "expr", path), `${path}/expr`),
  };
}

function parseBlock(rawNode: unknown, path: string): Block {
  const node = toXmlNode(rawNode, path);
  const rawParameters = getChildArray(node, "parameter");
  const rawAssigns = getChildArray(node, "assign");

  return {
    arity: parseRequiredIntAttribute(node, "arity", path),
    parameters: sortByOrder(
      rawParameters.map((item, index) =>
        parseParameter(item, `${path}/parameter[${String(index)}]`)
      )
    ),
    assigns: sortByOrder(
      rawAssigns.map((item, index) => parseAssign(item, `${path}/assign[${String(index)}]`))
    ),
  };
}

function parseMethod(rawNode: unknown, path: string): Method {
  const node = toXmlNode(rawNode, path);
  return {
    selector: getRequiredAttribute(node, "selector", path),
    block: parseBlock(getRequiredSingleChild(node, "block", path), `${path}/block`),
  };
}

function parseClassDef(rawNode: unknown, path: string): ClassDef {
  const node = toXmlNode(rawNode, path);
  const rawMethods = getChildArray(node, "method");
  return {
    name: getRequiredAttribute(node, "name", path),
    parent: getRequiredAttribute(node, "parent", path),
    methods: rawMethods.map((item, index) =>
      parseMethod(item, `${path}/method[${String(index)}]`)
    ),
  };
}

function parseProgram(rawNode: unknown): Program {
  const node = toXmlNode(rawNode, "program");
  const rawClasses = getChildArray(node, "class");

  return {
    language: getRequiredAttribute(node, "language", "program"),
    description: getOptionalAttribute(node, "description"),
    classes: rawClasses.map((item, index) =>
      parseClassDef(item, `program/class[${String(index)}]`)
    ),
  };
}

export class InvalidXmlError extends Error {
  public constructor(message: string) {
    super(message);
    this.name = "InvalidXmlError";
  }
}

export class ModelValidationError extends Error {
  public constructor(message: string) {
    super(message);
    this.name = "ModelValidationError";
  }
}

/**
 * Parses and validates a SOL-XML program from a string.
 */
export function parseProgramXml(xmlSource: string): Program {
  const isValidXml = XMLValidator.validate(xmlSource);
  if (isValidXml !== true) {
    throw new InvalidXmlError("Error parsing input XML");
  }

  const xmlParser = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: "@_",
    parseTagValue: false,
    parseAttributeValue: false,
    trimValues: false,
    ignoreDeclaration: true,
  });

  const parsed = xmlParser.parse(xmlSource) as unknown;
  const root = toXmlNode(parsed, "$root");
  return parseProgram(root["program"]);
}
